import csv
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagCollectionJob, PlaceTagEvidence, TagEnrichmentRequest
from recommendations.services.public_page_tag_evidence import fetch_public_page
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES
from recommendations.services.web_tag_evidence_provider import CATEGORY_TAGS
from recommendations.services.place_evidence_completeness import target_tags_for_gaps


MAX_TARGET_TAGS = 8
MAX_SOURCE_HINTS = 5
PREFLIGHT_POOL_MULTIPLIER = 2

# Tags whose supporting language is commonly present in public reviews and
# venue introductions come first. Facility facts remain useful candidates, but
# a run should not spend its only attempt on a very specific, rarely written
# detail when another missing recommendation dimension is researchable.
RESEARCHABILITY_PRIORITY = (
    "분위기좋음", "데이트좋음", "혼자이용좋음", "혼밥좋음", "대화하기좋음",
    "전망좋음", "사진찍기좋음", "디저트특화", "커피맛좋음", "가성비좋음",
    "대표메뉴뚜렷함", "여럿이먹기좋은메뉴", "메뉴선택폭넓음", "야외좌석",
    "반려동물동반", "단체석있음", "개별룸있음", "넓은테이블", "편한좌석",
    "자연채광좋음", "조용함", "웨이팅많음", "웨이팅적음", "예약필수",
    "시간제한있음", "좌석없음", "작업하기좋음", "노트북작업", "콘센트있음",
    "장기체류좋음", "좌석간격넓음", "유아의자있음", "유모차접근",
    "아이메뉴있음", "무단차접근", "엘리베이터있음", "주차어려움",
    "계단접근만가능", "테이크아웃전문", "와이파이있음", "무료와이파이",
)
RESEARCHABILITY_INDEX = {tag: index for index, tag in enumerate(RESEARCHABILITY_PRIORITY)}


def research_priority(place, launch_demands, *, quality_score=0):
    """Prefer source-ready launch gaps, then source-ready coverage, then cold launch gaps."""
    demand_score = sum(launch_demands.get(place.id, {}).values())
    identity_ready = bool(place.identity_success)
    tier = 0 if identity_ready and demand_score else 1 if identity_ready else 2
    return (
        tier,
        -demand_score,
        -quality_score,
        -int(place.evidence_success),
        -int(place.no_tag),
        place.name,
    )


class Command(BaseCommand):
    help = "Prepare a Busan-only Codex web research seed file without calling providers."

    def add_arguments(self, parser):
        parser.add_argument("--cafe", type=int, default=50)
        parser.add_argument("--restaurant", type=int, default=50)
        parser.add_argument("--output", default="tmp/codex_web_evidence_busan_pilot.json")
        parser.add_argument("--exclude-place-ids", default="")
        parser.add_argument("--preflight-source-hints", action="store_true")

    def handle(self, *args, **options):
        candidates = []
        allocation = Counter()
        requested_limits = {}
        excluded = {
            int(value) for value in str(options["exclude_place_ids"] or "").split(",")
            if value.strip().isdigit()
        }
        for category in ("cafe", "restaurant"):
            limit = max(0, int(options[category]))
            requested_limits[category] = limit
            pool_limit = limit * PREFLIGHT_POOL_MULTIPLIER if options["preflight_source_hints"] else limit
            rows = select_places(category, pool_limit, allocation, exclude_place_ids=excluded)
            if len(rows) < limit:
                raise CommandError("Only {} eligible {} places found".format(len(rows), category))
            candidates.extend(rows)
        preflight = {"checked": 0, "reachable": 0, "rejected": 0}
        if options["preflight_source_hints"]:
            preflight = preflight_source_hints(candidates)
        selected = []
        for category in ("cafe", "restaurant"):
            category_rows = [row for row in candidates if row["place"].category == category]
            selected.extend(prefer_source_ready(category_rows, requested_limits[category]))
        payload = {
            "region": "부산",
            "generated_at": timezone.now().isoformat(),
            "paid_api_calls": 0,
            "results": [seed_row(item) for item in selected],
        }
        path = Path(options["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_path = path.with_suffix(".csv")
        fields = list(payload["results"][0]) if payload["results"] else []
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(payload["results"])
        self.stdout.write(json.dumps({
            "places": len(selected),
            "candidate_pool": len(candidates),
            "categories": dict(Counter(row["place"].category for row in selected)),
            "target_tags": dict(Counter(row["tag"] for row in selected)),
            "launch_priority_places": sum(bool(row.get("launch_demand")) for row in selected),
            "source_hint_preflight": preflight,
            "json": str(path), "csv": str(csv_path),
        }, ensure_ascii=False))


def prefer_source_ready(rows, limit):
    """Keep selection order inside each tier while filling reachable pages first."""
    return sorted(rows, key=lambda row: not bool(row.get("source_hints")))[:limit]


def select_places(category, limit, allocation, *, exclude_place_ids=None):
    tags = CATEGORY_TAGS[category]
    exclude_place_ids = exclude_place_ids or set()
    launch_demands = launch_demand_context(category)
    launch_place_ids = set(launch_demands)
    identity_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__diagnostics__identity_matches__gt=0,
    )
    no_tag_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__miss_reason="NO_TAG_EXPRESSION",
    )
    evidence_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__evidences__gt=0,
    )
    places = list(Place.objects.filter(
        Q(address__startswith="부산") | Q(detail_location__startswith="부산"), category=category,
    ).exclude(id__in=exclude_place_ids).annotate(
        identity_success=Exists(identity_job), no_tag=Exists(no_tag_job),
        evidence_success=Exists(evidence_job),
    ).filter(Q(identity_success=True) | Q(id__in=launch_place_ids)).order_by(
        "-no_tag", "-evidence_success", "name",
    )[:5000])
    if category == "restaurant":
        scored = []
        for place in places:
            quality = restaurant_collection_quality(
                place, successful_jobs=int(place.evidence_success)
            )
            if quality["score"] < 8 or any(
                flag in quality["flags"]
                for flag in ("institutional_food_service", "contract_food_operator", "institutional_context")
            ):
                continue
            scored.append((quality["score"], place))
        places = [
            place for _score, place in sorted(
                scored,
                key=lambda item: research_priority(
                    item[1], launch_demands, quality_score=item[0],
                ),
            )
        ]
    else:
        places.sort(key=lambda place: research_priority(place, launch_demands))
    active = defaultdict(list)
    for row in PlaceTagEvidence.objects.filter(
        place_id__in=[place.id for place in places],
        tag__name__in=tags,
        polarity__in=("positive", "negative"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values(
        "place_id", "tag__name", "polarity", "source", "source_reference",
    ):
        active[row["place_id"]].append({**row, "tag_name": row["tag__name"]})
    selected = []
    seen_names = set()
    for place in places:
        normalized_name = "".join(str(place.name or "").lower().split())
        if len(normalized_name) < 3 or normalized_name in seen_names:
            continue
        missing = [
            tag for tag in target_tags_for_gaps(category, active[place.id], limit=len(tags))
            if tag in tags
        ]
        if not missing:
            continue
        ordered_missing = sorted(
            missing,
            key=lambda value: (
                -launch_demands.get(place.id, {}).get(value, 0),
                allocation[(category, value)],
                RESEARCHABILITY_INDEX.get(value, len(RESEARCHABILITY_INDEX)),
                tags.index(value),
            ),
        )
        tag = ordered_missing[0]
        allocation[(category, tag)] += 1
        seen_names.add(normalized_name)
        selected.append({
            "place": place,
            "tag": tag,
            "target_tags": [tag] + [value for value in ordered_missing if value != tag][:MAX_TARGET_TAGS - 1],
            "active_tags": sorted({row["tag_name"] for row in active[place.id]}),
            "source_hints": [],
            "launch_demand": launch_demands.get(place.id, {}),
        })
        if len(selected) >= limit:
            break
    source_hints = source_hints_for_places([row["place"].id for row in selected])
    for row in selected:
        row["source_hints"] = source_hints.get(row["place"].id, [])
    return selected


def launch_demand_context(category):
    location = Q(place__address__startswith="부산") | Q(place__detail_location__startswith="부산")
    requests = TagEnrichmentRequest.objects.filter(
        location, place__category=category, status="queued",
    ).values("place_id", "tag_name", "priority", "demand_count", "context")
    demands = defaultdict(dict)
    for request in requests:
        launch = (request.get("context") or {}).get("launch_quality")
        if not isinstance(launch, dict) or request["tag_name"] not in CATEGORY_TAGS.get(category, ()):
            continue
        demands[request["place_id"]][request["tag_name"]] = (
            int(request.get("priority") or 0) + int(request.get("demand_count") or 0)
        )
    return demands


def preflight_source_hints(selected, *, fetcher=fetch_public_page, max_attempts_per_place=2):
    """Keep only source hints that the production page fetcher can read."""
    candidates = []
    for row in selected:
        for hint in (row.get("source_hints") or [])[:max_attempts_per_place]:
            candidates.append((row, hint))
    if not candidates:
        return {"checked": 0, "reachable": 0, "rejected": 0}
    outcomes = {}
    with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as executor:
        futures = {executor.submit(fetcher, hint["url"]): (row, hint) for row, hint in candidates}
        for future in as_completed(futures):
            row, hint = futures[future]
            try:
                page = future.result()
            except Exception:
                page = {"ok": False}
            outcomes[(row["place"].id, hint["url"])] = page
    reachable = 0
    for row in selected:
        verified = []
        for hint in (row.get("source_hints") or [])[:max_attempts_per_place]:
            page = outcomes.get((row["place"].id, hint["url"])) or {}
            if not page.get("ok"):
                continue
            verified.append({
                **hint,
                "url": page.get("url") or hint["url"],
                "title": page.get("title") or hint.get("title") or "",
                "preflight_verified": True,
            })
            reachable += 1
        row["source_hints"] = verified
    return {
        "checked": len(candidates),
        "reachable": reachable,
        "rejected": len(candidates) - reachable,
    }


def source_hints_for_places(place_ids):
    hints = defaultdict(list)
    seen = defaultdict(set)
    evidences = PlaceTagEvidence.objects.filter(
        place_id__in=place_ids,
        source__in=WEB_EVIDENCE_SOURCES,
    ).exclude(source_reference="").order_by("-observed_at", "-id").values(
        "place_id", "source_reference", "evidence", "context",
    )
    for evidence in evidences:
        place_id = evidence["place_id"]
        url = str(evidence.get("source_reference") or "").strip()
        if len(hints[place_id]) >= MAX_SOURCE_HINTS or url in seen[place_id]:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        seen[place_id].add(url)
        context = evidence.get("context") or {}
        hints[place_id].append({
            "url": url,
            "title": str(context.get("source_title") or "")[:180],
            "description": str(evidence.get("evidence") or "")[:500],
            "hint_origin": "stored_evidence",
        })
    jobs = PlaceTagCollectionJob.objects.filter(
        place_id__in=place_ids,
        provider="naver_search",
        status="completed",
        stats__diagnostics__identity_matches__gt=0,
    ).order_by("-cycle_date", "-id").values("place_id", "stats")
    for job in jobs:
        place_id = job["place_id"]
        if len(hints[place_id]) >= MAX_SOURCE_HINTS:
            continue
        for attempt in (job.get("stats") or {}).get("search_attempts") or []:
            for result in attempt.get("results") or []:
                url = str(result.get("url") or "").strip()
                if not result.get("identity_matched") or not url.startswith(("http://", "https://")):
                    continue
                if url in seen[place_id]:
                    continue
                seen[place_id].add(url)
                hints[place_id].append({
                    "url": url,
                    "title": str(result.get("title") or "")[:180],
                    "description": str(result.get("description") or "")[:500],
                    "hint_origin": "naver_identity_match",
                })
                if len(hints[place_id]) >= MAX_SOURCE_HINTS:
                    break
            if len(hints[place_id]) >= MAX_SOURCE_HINTS:
                break
    return hints


def seed_row(item):
    place = item["place"]
    district = next((part for part in str(place.address or "").split() if part.endswith(("구", "군"))), "")
    return {
        "place_id": place.id,
        "place_name": place.name,
        "category": place.category,
        "address": place.address,
        "district": district,
        "existing_active_tags": "|".join(item["active_tags"]),
        "target_tag": item["tag"],
        "target_tags": item["target_tags"],
        "source_hints": item["source_hints"],
        "selection_reason": "launch_quality_gap" if item.get("launch_demand") else "coverage_gap",
        "launch_demand_tags": sorted(item.get("launch_demand") or {}, key=(item.get("launch_demand") or {}).get, reverse=True),
        "extracted_tag": "",
        "polarity": "",
        "source_url": "",
        "source_title": "",
        "source_domain": "",
        "source_type": "",
        "evidence_span": "",
        "published_at": "unknown",
        "retrieved_at": "",
        "identity_status": "",
        "identity_confidence": 0,
        "evidence_confidence_candidate": 0,
        "freshness": "unknown",
        "page_verified": False,
        "source_candidate_only": False,
        "research_status": "NO_RESULT",
        "notes": "",
    }
