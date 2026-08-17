import json
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage
from recommendations.services.adaptive_budget import recommend_scaled_budget
from recommendations.services.place_tag_collection import requested_tags_for_category


REGIONS = ("서울", "부산", "인천", "대구", "대전", "광주", "울산")
CATEGORIES = ("cafe", "restaurant")


class Command(BaseCommand):
    help = "Report candidate-first collection pools, measured ROI, and request-budget simulations."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/collection_roi.json")
        parser.add_argument("--daily-places", default="5000,7500,10000")

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()
        quota = ProviderQuotaUsage.objects.filter(
            provider="naver_search", usage_date=today,
        ).values().first() or {}
        attempted = defaultdict(set)
        for place_id, context in PlaceTagCollectionJob.objects.filter(
            cycle_date=today, context__targeted_attempts__isnull=False,
        ).values_list("place_id", "context"):
            for key in ((context or {}).get("targeted_attempts") or {}):
                attempted[place_id].add(key)

        pool = Counter()
        pairs = []
        active_same_tag = PlaceTagEvidence.objects.filter(
            place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"),
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        for region in REGIONS:
            for category in CATEGORIES:
                tags = requested_tags_for_category(category)
                rows = PlaceTag.objects.filter(
                    place__address__startswith=region,
                    place__category=category,
                    status__in=("candidate", "needs_verification"),
                    tag__name__in=tags,
                ).annotate(has_active=Exists(active_same_tag)).filter(
                    has_active=False,
                ).values_list("place_id", "tag__name").distinct()
                for place_id, tag_name in rows.iterator():
                    key = (region, category, tag_name)
                    pool[key] += 1
                    pairs.append((place_id, tag_name, key))

        unattempted = Counter()
        for place_id, tag_name, key in pairs:
            attempts = attempted.get(place_id, set())
            if not any(name.startswith("candidate:") for name in attempts):
                unattempted[key] += 1

        bucket_history = defaultdict(lambda: Counter(calls=0, evidence=0, active_evidence=0, failures=0, rate_limited=0))
        adaptive_jobs = PlaceTagCollectionJob.objects.filter(
            status="completed", context__budget_bucket__isnull=False,
        ).order_by("-id")[:5000]
        job_count = 0
        for job in adaptive_jobs:
            job_count += 1
            bucket = (job.context or {}).get("budget_bucket") or "unknown"
            stats = job.stats or {}
            bucket_history[bucket]["calls"] += int(stats.get("requests") or 0)
            bucket_history[bucket]["evidence"] += int(stats.get("new_evidences") or stats.get("evidences") or 0)
            bucket_history[bucket]["active_evidence"] += int(stats.get("new_active_evidences") or 0)
            bucket_history[bucket]["failures"] += int(bool(job.error_code and job.error_code != "insufficient_evidence"))
            bucket_history[bucket]["rate_limited"] += int(job.error_code == "rate_limited")
        targeted_job_count = 0
        for context in PlaceTagCollectionJob.objects.filter(
            context__targeted_metrics__isnull=False,
        ).order_by("-id").values_list("context", flat=True)[:5000]:
            targeted_job_count += 1
            for bucket, metrics in ((context or {}).get("targeted_metrics") or {}).items():
                for key in ("calls", "evidence", "active_evidence", "failures", "rate_limited"):
                    bucket_history[bucket][key] += int((metrics or {}).get(key) or 0)
        calls = sum(row["calls"] for row in bucket_history.values())
        measured_places = job_count + targeted_job_count
        calls_per_place = calls / measured_places if measured_places else 1
        simulations = {}
        weights = settings.TAG_COLLECTION_BUDGET_WEIGHTS
        for value in options["daily_places"].split(","):
            places = max(1, int(value.strip()))
            expected_calls = round(places * calls_per_place)
            simulations[str(places)] = {
                "expected_calls": expected_calls,
                "quota_usage_pct": round(expected_calls / settings.TAG_COLLECTION_DAILY_API_LIMIT * 100, 2),
                "within_90pct_safety": expected_calls <= settings.TAG_COLLECTION_DAILY_API_LIMIT * settings.TAG_COLLECTION_QUOTA_PERCENT / 100,
                "bucket_calls": {
                    key: round(expected_calls * weight / max(1, sum(weights.values())))
                    for key, weight in weights.items()
                },
            }
        recent_cycles = []
        for cycle_date in PlaceTagCollectionJob.objects.filter(
            status="completed", context__adaptive=True,
        ).order_by("-cycle_date").values_list("cycle_date", flat=True).distinct()[:3]:
            rows = PlaceTagCollectionJob.objects.filter(cycle_date=cycle_date, status="completed", context__adaptive=True)
            recent_cycles.append({
                "calls": sum(int((row.stats or {}).get("requests") or 0) for row in rows),
                "active_evidence": sum(int((row.stats or {}).get("new_active_evidences") or 0) for row in rows),
                "failures": rows.exclude(error_code__in=("", "insufficient_evidence")).count(),
                "rate_limited": rows.filter(error_code="rate_limited").count(),
            })
        report = {
            "generated_at": now.isoformat(),
            "quota": quota,
            "candidate_pairs": [
                {"region": key[0], "category": key[1], "tag": key[2], "pairs": count, "unattempted_today": unattempted[key]}
                for key, count in sorted(pool.items())
            ],
            "candidate_pair_total": sum(pool.values()),
            "candidate_unattempted_today": sum(unattempted.values()),
            "measured_bucket_roi": {
                key: {
                    **dict(row),
                    "evidence_per_call": round(row["evidence"] / row["calls"], 4) if row["calls"] else None,
                    "active_per_call": round(row["active_evidence"] / row["calls"], 4) if row["calls"] else None,
                }
                for key, row in bucket_history.items()
            },
            "calls_per_place": round(calls_per_place, 4),
            "budget_weights": weights,
            "daily_simulations": simulations,
            "scaling": recommend_scaled_budget(recent_cycles, current_budget=7500),
        }
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
