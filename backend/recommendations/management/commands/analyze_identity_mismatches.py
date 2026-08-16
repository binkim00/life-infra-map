import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from recommendations.models import PlaceTagCollectionJob, ProviderQuotaUsage
from recommendations.services.identity_diagnostics import choose_place_failure
from recommendations.services.naver_search_provider import _clean_html, _request_channel, _safe_text
from recommendations.services.naver_tag_evidence_provider import SEARCH_KEYWORDS
from recommendations.services.place_tag_collection import build_collection_query, collection_profile
from recommendations.services.provider_rate_limit import acquire_provider_slot


class Command(BaseCommand):
    help = "Re-query failed jobs and classify actual identity mismatch causes without storing raw results in DB."

    def add_arguments(self, parser):
        parser.add_argument("--latest", type=int, default=500)
        parser.add_argument("--output", default="tmp/identity_mismatch_analysis.json")
        parser.add_argument("--csv", default="tmp/identity_mismatch_analysis.csv")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--category", default="")

    def handle(self, *args, **options):
        job_ids = PlaceTagCollectionJob.objects.order_by("-id").values_list("id", flat=True)[:options["latest"]]
        queryset = PlaceTagCollectionJob.objects.filter(
                id__in=job_ids,
                stats__miss_reason="IDENTITY_MISMATCH",
            ).select_related("place").order_by("-id")
        if options["category"]:
            queryset = queryset.filter(place__category=options["category"])
        jobs = list(queryset)
        if options["limit"]:
            jobs = jobs[:options["limit"]]
        rows = []
        reason_counts = Counter()
        category_counts = defaultdict(Counter)
        industry_counts = defaultdict(Counter)
        requests = failures = 0
        for job in jobs:
            results = []
            for pack_name, tags in collection_profile(job.place.category):
                query = build_collection_query(job.place, SEARCH_KEYWORDS.get(tags[0], tags[0]))
                if not reserve_request():
                    raise CommandError("Naver diagnostic quota exhausted")
                try:
                    acquire_provider_slot("naver_search")
                    payload = _request_channel("blog", query)
                    requests += 1
                    settle_request(True)
                except Exception:
                    failures += 1
                    settle_request(False)
                    continue
                for item in (payload or {}).get("items") or []:
                    title = _clean_html(item.get("title"), 180)
                    summary = _clean_html(item.get("description"), 500)
                    results.append({
                        "query": query,
                        "pack": pack_name,
                        "title": title,
                        "summary": summary,
                        "url": _safe_text(item.get("link"), 500),
                        "text": "{} {}".format(title, summary),
                    })
            outcome = choose_place_failure(job.place, results)
            reason_counts[outcome["reason"]] += 1
            category_counts[job.place.category][outcome["reason"]] += 1
            raw = job.place.raw if isinstance(job.place.raw, dict) else {}
            industry = str(
                raw.get("industry_middle_name")
                or raw.get("industry_minor_name")
                or raw.get("business_type")
                or "UNKNOWN"
            ).strip()
            industry_counts[industry][outcome["reason"]] += 1
            best = outcome["best"] or {}
            identity = best.get("identity") or {}
            rows.append({
                "job_id": job.id,
                "place_id": job.place_id,
                "category": job.place.category,
                "source": job.place.source,
                "industry_middle": raw.get("industry_middle_name", ""),
                "industry_minor": raw.get("industry_minor_name", ""),
                "place_name": job.place.name,
                "place_address": job.place.address,
                "reason": outcome["reason"],
                "identity_score": identity.get("score", 0),
                "identity_signals": json.dumps(identity.get("signals", {}), ensure_ascii=False),
                "query": best.get("query", ""),
                "result_title": best.get("title", ""),
                "result_summary": best.get("summary", ""),
                "source_url": best.get("url", ""),
                "result_regions": ",".join(identity.get("result_regions", [])),
            })
        write_csv(options["csv"], rows)
        report = {
            "generated_at": timezone.now().isoformat(),
            "jobs": len(jobs),
            "requests": requests,
            "request_failures": failures,
            "reasons": dict(reason_counts),
            "by_category": {key: dict(value) for key, value in sorted(category_counts.items())},
            "by_industry": {key: dict(value) for key, value in sorted(industry_counts.items())},
            "examples": examples_by_reason(rows),
        }
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        path.write_text(rendered, encoding="utf-8")
        output_encoding = getattr(getattr(self.stdout, "_out", None), "encoding", None) or "utf-8"
        self.stdout.write(
            rendered.encode(output_encoding, errors="backslashreplace").decode(output_encoding)
        )


def reserve_request():
    with transaction.atomic():
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider="naver_search",
            usage_date=timezone.localdate(),
            defaults={"daily_limit": settings.TAG_COLLECTION_DAILY_API_LIMIT},
        )
        safe_limit = quota.daily_limit * settings.TAG_COLLECTION_QUOTA_PERCENT // 100
        if quota.request_count + quota.reserved_count >= safe_limit:
            return False
        quota.reserved_count += 1
        quota.save(update_fields=["reserved_count", "updated_at"])
    return True


def settle_request(succeeded):
    ProviderQuotaUsage.objects.filter(provider="naver_search", usage_date=timezone.localdate()).update(
        reserved_count=F("reserved_count") - 1,
        request_count=F("request_count") + 1,
        success_count=F("success_count") + int(succeeded),
        failed_count=F("failed_count") + int(not succeeded),
    )


def write_csv(output, rows):
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["job_id", "place_id", "reason"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def examples_by_reason(rows):
    grouped = defaultdict(list)
    for row in rows:
        if len(grouped[row["reason"]]) < 3:
            grouped[row["reason"]].append({
                key: row[key] for key in (
                    "place_id", "category", "place_name", "place_address",
                    "identity_score", "result_title", "source_url",
                )
            })
    return dict(grouped)
