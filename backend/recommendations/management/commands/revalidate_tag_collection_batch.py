import json
import time
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import save_place_candidate_evidence
from recommendations.models import PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage
from recommendations.services.evidence_scoring import parse_observed_date
from recommendations.services.place_tag_collection import collect_naver_place_evidence


class Command(BaseCommand):
    help = "Re-run a bounded existing batch for before/after identity and evidence comparison."

    def add_arguments(self, parser):
        parser.add_argument("--latest", type=int, default=500)
        parser.add_argument("--output", default="tmp/tag_collection_revalidation.json")

    def handle(self, *args, **options):
        job_ids = PlaceTagCollectionJob.objects.order_by("-id").values_list("id", flat=True)[:options["latest"]]
        jobs = list(PlaceTagCollectionJob.objects.filter(id__in=job_ids).select_related("place").order_by("id"))
        evidence_before = PlaceTagEvidence.objects.count()
        place_tags_before = PlaceTag.objects.count()
        misses = Counter()
        hit_places = identity_pass_places = requests = failures = rate_limited = 0
        started = time.perf_counter()
        for job in jobs:
            reserved = reserve_requests(job.planned_requests)
            if not reserved:
                raise CommandError("Naver quota exhausted during revalidation")
            result = collect_naver_place_evidence(job.place, job.requested_tags, allow_ai=False)
            made = min(reserved, int(result.get("requests") or 0))
            error = result.get("error") or ""
            settle_requests(reserved, made, succeeded=error in {"", "insufficient_evidence"}, rate_limited=error == "rate_limited")
            requests += made
            failures += int(error not in {"", "insufficient_evidence"})
            rate_limited += int(error == "rate_limited")
            diagnostics = result.get("diagnostics") or {}
            identity_pass_places += int(int(diagnostics.get("identity_matches") or 0) > 0)
            evidences = result.get("evidences") or []
            hit_places += int(bool(evidences))
            if not evidences:
                misses[result.get("miss_reason") or "OTHER"] += 1
            for evidence in evidences:
                save_place_candidate_evidence(
                    job.place,
                    evidence["tag_name"],
                    evidence,
                    observed_at=parse_observed_date(evidence.get("observed_date")) or timezone.now(),
                )
        report = {
            "places": len(jobs),
            "identity_pass_places": identity_pass_places,
            "identity_failed_places": len(jobs) - identity_pass_places,
            "places_with_web_evidence": hit_places,
            "web_evidence_hit_rate": round(hit_places / len(jobs), 4) if jobs else None,
            "miss_reasons": dict(misses),
            "api_requests": requests,
            "api_failures": failures,
            "rate_limited": rate_limited,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "evidence_before": evidence_before,
            "evidence_after": PlaceTagEvidence.objects.count(),
            "new_evidence": PlaceTagEvidence.objects.count() - evidence_before,
            "place_tags_before": place_tags_before,
            "place_tags_after": PlaceTag.objects.count(),
            "new_place_tags": PlaceTag.objects.count() - place_tags_before,
        }
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))


def reserve_requests(count):
    with transaction.atomic():
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider="naver_search",
            usage_date=timezone.localdate(),
            defaults={"daily_limit": settings.TAG_COLLECTION_DAILY_API_LIMIT},
        )
        safe_limit = quota.daily_limit * settings.TAG_COLLECTION_QUOTA_PERCENT // 100
        if quota.request_count + quota.reserved_count + count > safe_limit:
            return 0
        quota.reserved_count += count
        quota.save(update_fields=["reserved_count", "updated_at"])
    return count


def settle_requests(reserved, made, *, succeeded, rate_limited):
    ProviderQuotaUsage.objects.filter(provider="naver_search", usage_date=timezone.localdate()).update(
        reserved_count=F("reserved_count") - reserved,
        request_count=F("request_count") + made,
        success_count=F("success_count") + (made if succeeded else 0),
        failed_count=F("failed_count") + (0 if succeeded else made),
        rate_limited_count=F("rate_limited_count") + (made if rate_limited else 0),
    )
