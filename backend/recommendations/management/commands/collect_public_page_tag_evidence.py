import json
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import save_place_candidate_evidence
from recommendations.models import Place, PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage
from recommendations.services.place_tag_collection import _request_channel, build_collection_query
from recommendations.services.public_page_tag_evidence import (
    extract_page_evidences, fetch_public_page, source_type,
)
from recommendations.services.web_tag_evidence_provider import CATEGORY_TAGS, canonical_url, is_blocked_source


QUERY_CLUSTERS = {
    "cafe": (
        ("work", ("콘센트", "와이파이", "노트북 공부", "카공 작업")),
        ("solo_long", ("혼자 혼카페", "오래 좌석")),
        ("social", ("조용 대화", "분위기 데이트")),
    ),
    "restaurant": (
        ("solo", ("혼밥 혼자", "1인 바좌석")),
        ("social", ("분위기 데이트", "소개팅 조용 대화")),
        ("waiting", ("웨이팅 대기",)),
    ),
}


class Command(BaseCommand):
    help = "Discover and fetch public pages to enrich Busan cafe/restaurant tag evidence."

    def add_arguments(self, parser):
        parser.add_argument("--category", choices=("cafe", "restaurant", "both"), default="both")
        parser.add_argument("--places", type=int, default=100)
        parser.add_argument("--max-queries", type=int, default=2)
        parser.add_argument("--max-fetches", type=int, default=200)
        parser.add_argument("--max-pages-per-place", type=int, default=2)
        parser.add_argument("--pool", choices=("balanced", "gap", "new_coverage"), default="balanced")
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--output", default="tmp/public_page_tag_evidence_checkpoint.json")

    def handle(self, *args, **options):
        categories = ("cafe", "restaurant") if options["category"] == "both" else (options["category"],)
        places = select_places(categories, max(1, options["places"]), pool_mode=options["pool"])
        if not options["execute"]:
            self.stdout.write(json.dumps({
                "dry_run": True, "places": len(places),
                "categories": dict(Counter(place.category for place in places)),
                "sample": [{"id": p.id, "name": p.name, "category": p.category, "address": p.address} for p in places[:20]],
            }, ensure_ascii=False, indent=2))
            return
        report = run_collection(
            places,
            max_queries=max(1, min(3, options["max_queries"])),
            max_fetches=max(1, options["max_fetches"]),
            max_pages_per_place=max(1, min(5, options["max_pages_per_place"])),
        )
        output = Path(settings.BASE_DIR) / options["output"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.stdout.write(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS("Checkpoint: {}".format(output)))


def select_places(categories, limit, *, pool_mode="balanced"):
    location = Q(address__startswith="부산") | Q(detail_location__startswith="부산")
    now = timezone.now()
    active = Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    selected = []
    seen = set()
    per_category = max(1, limit // len(categories))
    for category in categories:
        base = Place.objects.filter(location, category=category).exclude(
            tag_collection_jobs__provider="public_page_fetch",
            tag_collection_jobs__cycle_date=timezone.localdate(),
        )
        evidence_place_ids = PlaceTagEvidence.objects.filter(place__in=base).values_list("place_id", flat=True).distinct()
        identity_place_ids = PlaceTagCollectionJob.objects.filter(
            place__in=base, status="completed", stats__diagnostics__identity_matches__gt=0,
        ).order_by("-updated_at").values_list("place_id", flat=True).distinct()
        gap_pools = (
            base.filter(id__in=identity_place_ids).filter(id__in=evidence_place_ids).order_by("id"),
            base.filter(id__in=evidence_place_ids).order_by("id"),
        )
        new_pools = (
            base.filter(id__in=identity_place_ids).exclude(id__in=evidence_place_ids).order_by("id"),
            base.exclude(id__in=evidence_place_ids).order_by("id"),
        )
        if pool_mode == "gap":
            pools = gap_pools
        elif pool_mode == "new_coverage":
            pools = new_pools
        else:
            pools = (gap_pools[0], new_pools[0], gap_pools[1], new_pools[1])
        district_queues = defaultdict(deque)
        pool_target = per_category * 3
        for pool in pools:
            for place in pool[:pool_target]:
                if place.id in seen or not high_quality_name(place.name):
                    continue
                district = district_name(place.address or place.detail_location)
                district_queues[district].append(place)
        category_rows = []
        districts = deque(sorted(district_queues))
        while districts and len(category_rows) < per_category:
            district = districts.popleft()
            queue = district_queues[district]
            if queue:
                place = queue.popleft()
                if place.id not in seen:
                    selected.append(place)
                    category_rows.append(place)
                    seen.add(place.id)
            if queue:
                districts.append(district)
    return selected[:limit]


def high_quality_name(value):
    compact = "".join(character for character in str(value or "") if character.isalnum())
    return len(compact) >= 3


def run_collection(places, *, max_queries, max_fetches, max_pages_per_place):
    started = timezone.now()
    before = snapshot(places)
    session = requests.Session()
    robots_cache = {}
    seen_urls = set()
    rows = []
    source_metrics = defaultdict(Counter)
    summary = Counter({"places": len(places)})
    processed_place_ids = []
    stop = False
    for place in places:
        if stop:
            break
        processed_place_ids.append(place.id)
        missing = missing_tags(place)
        query_rows = adaptive_queries(place, missing)[:max_queries]
        place_pages = 0
        place_had_evidence = False
        for cluster, keyword in query_rows:
            if place_pages >= max_pages_per_place or summary["fetch_attempts"] >= max_fetches:
                break
            if not reserve_naver_request():
                stop = True
                summary["quota_stopped"] += 1
                break
            query = build_collection_query(place, keyword)
            try:
                payload = _request_channel("blog", query)
                settle_naver_request(True)
                summary["naver_calls"] += 1
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                settle_naver_request(False, rate_limited=status == 429)
                summary["naver_calls"] += 1
                summary["naver_errors"] += 1
                if status == 429:
                    stop = True
                continue
            except requests.RequestException:
                settle_naver_request(False)
                summary["naver_calls"] += 1
                summary["naver_errors"] += 1
                continue
            items = (payload or {}).get("items") or []
            summary["search_results"] += len(items)
            for rank, item in enumerate(items[:5], start=1):
                if place_pages >= max_pages_per_place or summary["fetch_attempts"] >= max_fetches:
                    break
                url = canonical_url(item.get("link"))
                if not url or url in seen_urls or is_blocked_source(url):
                    summary["url_rejected_or_duplicate"] += 1
                    continue
                seen_urls.add(url)
                domain = urlsplit(url).netloc.lower()
                metric = source_metrics[domain]
                metric["search_results"] += 1
                metric["fetch_attempts"] += 1
                summary["fetch_attempts"] += 1
                fetched = fetch_public_page(url, session=session, robots_cache=robots_cache)
                audit = {
                    "place_id": place.id, "place_name": place.name, "category": place.category,
                    "address": place.address, "district": district_name(place.address),
                    "target_cluster": cluster, "query": query, "result_rank": rank,
                    "url": url, "domain": domain, "fetch_error": fetched.get("error") or "",
                    "identity_score": 0, "identity_matched": False, "evidences": [],
                }
                rows.append(audit)
                if not fetched.get("ok"):
                    metric[fetched.get("error") or "FETCH_FAILED"] += 1
                    summary[fetched.get("error") or "fetch_failed"] += 1
                    if fetched.get("error") == "RATE_LIMITED":
                        break
                    continue
                place_pages += 1
                metric["fetch_success"] += 1
                summary["fetch_success"] += 1
                extracted = extract_page_evidences(place, fetched, query=query, result_rank=rank)
                audit["identity_score"] = extracted["identity"]["score"]
                audit["identity_matched"] = extracted["identity"]["matched"]
                if not extracted["identity"]["matched"]:
                    metric["identity_mismatch"] += 1
                    summary["identity_mismatch"] += 1
                    continue
                metric["identity_success"] += 1
                summary["identity_success"] += 1
                if not extracted["evidences"]:
                    metric["no_feature"] += 1
                    summary["no_feature"] += 1
                    continue
                for evidence in extracted["evidences"]:
                    observed_at = parse_observed(evidence.get("observed_date"))
                    _, created = save_place_candidate_evidence(
                        place, evidence["tag_name"], evidence, observed_at=observed_at,
                    )
                    audit["evidences"].append({
                        "tag": evidence["tag_name"], "polarity": evidence["polarity"],
                        "strength": evidence["extraction"].get("strength"),
                        "span": evidence["evidence_summary"], "created": created,
                        "source_url": evidence["source_url"],
                        "source_type": source_type(evidence["source_url"]),
                    })
                    metric["evidence"] += int(created)
                    summary["new_evidence"] += int(created)
                    summary["evidence_candidates"] += 1
                    if created:
                        place_had_evidence = True
                if place_had_evidence:
                    break
            if place_had_evidence:
                break
    after = snapshot(places)
    summary["finished_at"] = timezone.now().isoformat()
    summary["new_evidence_place"] = after["evidence_place"] - before["evidence_place"]
    summary["new_active_evidence"] = after["active_evidence"] - before["active_evidence"]
    summary["new_active_evidence_place"] = after["active_evidence_place"] - before["active_evidence_place"]
    summary["new_place_tag"] = after["place_tag"] - before["place_tag"]
    for domain, metric in source_metrics.items():
        metric["active_evidence"] = sum(
            1 for row in rows if row["domain"] == domain for evidence in row["evidences"]
            if evidence["created"] and evidence["strength"] == "DIRECT"
        )
    for place_id in processed_place_ids:
        PlaceTagCollectionJob.objects.update_or_create(
            place_id=place_id, provider="public_page_fetch", cycle_date=timezone.localdate(),
            defaults={
                "status": "completed", "priority": 1, "planned_requests": 0,
                "requested_tags": [],
                "stats": {"checkpoint": "public_page", "completed_at": summary["finished_at"]},
                "context": {"region": "부산광역시", "source": "public_page_fetch"},
            },
        )
    return {
        "started_at": started.isoformat(), "summary": dict(summary),
        "before": before, "after": after,
        "source_metrics": {key: dict(value) for key, value in source_metrics.items()},
        "rows": rows,
    }


def adaptive_queries(place, missing):
    clusters = QUERY_CLUSTERS.get(place.category, ())
    tag_to_cluster = {
        "무료와이파이": "work", "콘센트있음": "work", "노트북작업": "work", "작업하기좋음": "work",
        "장기체류좋음": "solo_long", "혼자이용좋음": "solo_long" if place.category == "cafe" else "solo",
        "혼밥좋음": "solo", "분위기좋음": "social", "데이트좋음": "social", "대화하기좋음": "social",
        "조용함": "social", "웨이팅적음": "waiting",
    }
    needed = Counter(tag_to_cluster.get(tag) for tag in missing)
    priority_order = {
        "cafe": {"work": 0, "solo_long": 1, "social": 2},
        "restaurant": {"solo": 0, "social": 1, "waiting": 2},
    }.get(place.category, {})
    ordered = sorted(
        clusters,
        key=lambda row: (-needed.get(row[0], 0), priority_order.get(row[0], 99)),
    )
    result = []
    for name, keywords in ordered:
        if needed.get(name, 0) < 1:
            continue
        result.extend((name, keyword) for keyword in keywords)
    return result


def missing_tags(place):
    now = timezone.now()
    active_names = set(PlaceTagEvidence.objects.filter(
        place=place, polarity="positive",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).values_list("tag__name", flat=True))
    return [tag for tag in CATEGORY_TAGS.get(place.category, ()) if tag not in active_names]


def reserve_naver_request():
    safe_limit = settings.TAG_COLLECTION_DAILY_API_LIMIT * settings.TAG_COLLECTION_QUOTA_PERCENT // 100
    with transaction.atomic():
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider="naver_search", usage_date=timezone.localdate(),
            defaults={"daily_limit": settings.TAG_COLLECTION_DAILY_API_LIMIT},
        )
        if quota.request_count + quota.reserved_count + 1 > safe_limit:
            return False
        quota.reserved_count += 1
        quota.save(update_fields=["reserved_count", "updated_at"])
    return True


def settle_naver_request(succeeded, *, rate_limited=False):
    ProviderQuotaUsage.objects.filter(
        provider="naver_search", usage_date=timezone.localdate(),
    ).update(
        reserved_count=F("reserved_count") - 1,
        request_count=F("request_count") + 1,
        success_count=F("success_count") + int(succeeded),
        failed_count=F("failed_count") + int(not succeeded),
        rate_limited_count=F("rate_limited_count") + int(rate_limited),
    )


def snapshot(places):
    ids = [place.id for place in places]
    now = timezone.now()
    active = Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    evidence = PlaceTagEvidence.objects.filter(place_id__in=ids)
    return {
        "evidence": evidence.count(),
        "active_evidence": evidence.filter(active).count(),
        "evidence_place": evidence.values("place_id").distinct().count(),
        "active_evidence_place": evidence.filter(active).values("place_id").distinct().count(),
        "place_tag": PlaceTag.objects.filter(place_id__in=ids).count(),
    }


def parse_observed(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def district_name(value):
    parts = str(value or "").split()
    return parts[1] if len(parts) > 1 else "UNKNOWN"
