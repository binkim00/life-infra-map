import json
import time
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import (
    save_place_candidate_evidence,
)
from recommendations.models import (
    Place,
    PlaceTag,
    PlaceTagCollectionJob,
    PlaceTagEvidence,
    ProviderQuotaUsage,
)
from recommendations.services.adaptive_tag_collection import FEATURE_QUERY_CLUSTERS
from recommendations.services.evidence_scoring import parse_observed_date
from recommendations.services.place_tag_collection import (
    collect_naver_place_evidence,
    requested_tags_for_category,
)
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


class Command(BaseCommand):
    help = "Evaluate Discovery and sparse feature query packs on the same safe sample."

    def add_arguments(self, parser):
        parser.add_argument("--sample-size", type=int, default=50)
        parser.add_argument("--sample-offset", type=int, default=0)
        parser.add_argument("--region", default="서울")
        parser.add_argument("--category", default="cafe")
        parser.add_argument("--output", default="tmp/sparse_query_pack_ab.json")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--pool", choices=("no_tag", "candidate", "stale"), default="no_tag"
        )
        parser.add_argument(
            "--packs",
            default="",
            help="Optional comma-separated pack names (discovery, work_sparse, solo, long_stay, talk).",
        )

    def handle(self, *args, **options):
        if options["pool"] in {"candidate", "stale"}:
            target_tags = FEATURE_QUERY_CLUSTERS[0][1]
            active_same_tag = PlaceTagEvidence.objects.filter(
                place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"),
                expires_at__gt=timezone.now(),
            )
            if options["pool"] == "candidate":
                hints = PlaceTag.objects.filter(
                    place__category=options["category"],
                    place__address__startswith=options["region"],
                    status__in=("candidate", "needs_verification"),
                    tag__name__in=target_tags,
                )
            else:
                hints = PlaceTagEvidence.objects.filter(
                    place__category=options["category"],
                    place__address__startswith=options["region"],
                    source__in=WEB_EVIDENCE_SOURCES,
                    expires_at__lte=timezone.now(),
                    tag__name__in=target_tags,
                )
            place_ids = hints.annotate(has_active=Exists(active_same_tag)).filter(
                has_active=False,
            ).order_by("-id").values_list("place_id", flat=True).distinct()
            jobs = (
                type("CandidateRow", (), {"place_id": place.id, "place": place})
                for place in Place.objects.filter(id__in=place_ids).order_by("-id")
            )
        else:
            jobs = PlaceTagCollectionJob.objects.filter(
                place__category=options["category"],
                place__address__startswith=options["region"],
                stats__miss_reason="NO_TAG_EXPRESSION",
                status="completed",
            ).select_related("place").order_by("-id")
        places = []
        seen = set()
        skipped = 0
        for job in jobs:
            if job.place_id in seen:
                continue
            seen.add(job.place_id)
            if skipped < max(0, options["sample_offset"]):
                skipped += 1
                continue
            places.append(job.place)
            if len(places) >= options["sample_size"]:
                break
        if not places:
            raise CommandError("No matching NO_TAG_EXPRESSION sample exists.")

        packs = [("discovery", None)] + list(FEATURE_QUERY_CLUSTERS[:4])
        selected_packs = {
            value.strip() for value in options["packs"].split(",") if value.strip()
        }
        if selected_packs:
            known = {name for name, _ in packs}
            unknown = selected_packs - known
            if unknown:
                raise CommandError("Unknown query packs: " + ", ".join(sorted(unknown)))
            packs = [row for row in packs if row[0] in selected_packs]
        report = {
            "mode": "apply" if options["apply"] else "measure_only",
            "sample_places": len(places),
            "region": options["region"],
            "category": options["category"],
            "pool": options["pool"],
            "packs": {},
            "api_calls": 0,
            "started_at": timezone.now().isoformat(),
        }
        started = time.perf_counter()
        for pack_name, pack_tags in packs:
            stats = Counter()
            before_evidence = PlaceTagEvidence.objects.count()
            before_active_evidence = PlaceTagEvidence.objects.filter(
                expires_at__gt=timezone.now(),
            ).count()
            before_tags = PlaceTag.objects.count()
            for place in places:
                if not _reserve_request():
                    raise CommandError("Naver safe quota exhausted during A/B evaluation.")
                if pack_name == "discovery":
                    result = collect_naver_place_evidence(
                        place,
                        requested_tags_for_category(place.category),
                        strategy="adaptive",
                        targeted_tags=(),
                        allow_ai=False,
                    )
                else:
                    result = collect_naver_place_evidence(
                        place,
                        requested_tags_for_category(place.category),
                        strategy="targeted_only",
                        targeted_tags=pack_tags,
                        allow_ai=False,
                    )
                made = min(1, int(result.get("requests") or 0))
                error = result.get("error") or ""
                _settle_request(made, error)
                stats["calls"] += made
                stats["places"] += 1
                stats["failures"] += int(error not in {"", "insufficient_evidence"})
                stats["rate_limited"] += int(error == "rate_limited")
                diagnostics = result.get("diagnostics") or {}
                stats["search_result_places"] += int(int(diagnostics.get("search_results") or 0) > 0)
                stats["identity_pass_places"] += int(int(diagnostics.get("identity_matches") or 0) > 0)
                evidences = result.get("evidences") or []
                stats["evidence_places"] += int(bool(evidences))
                stats["evidence_rows"] += len(evidences)
                if not evidences:
                    stats[result.get("miss_reason") or "OTHER"] += 1
                if options["apply"]:
                    for evidence in evidences:
                        observed_at = parse_observed_date(evidence.get("observed_date")) or timezone.now()
                        save_place_candidate_evidence(
                            place, evidence["tag_name"], evidence, observed_at=observed_at,
                        )
            calls = stats["calls"]
            report["packs"][pack_name] = {
                **dict(stats),
                "calls_per_place": round(calls / len(places), 4),
                "evidence_per_call": round(stats["evidence_rows"] / calls, 4) if calls else 0,
                "evidence_place_per_call": round(stats["evidence_places"] / calls, 4) if calls else 0,
                "new_evidence": PlaceTagEvidence.objects.count() - before_evidence,
                "new_active_evidence": PlaceTagEvidence.objects.filter(
                    expires_at__gt=timezone.now(),
                ).count() - before_active_evidence,
                "new_place_tags": PlaceTag.objects.count() - before_tags,
            }
            report["api_calls"] += calls
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))


def _reserve_request():
    with transaction.atomic():
        quota, _ = ProviderQuotaUsage.objects.select_for_update().get_or_create(
            provider="naver_search",
            usage_date=timezone.localdate(),
            defaults={"daily_limit": settings.TAG_COLLECTION_DAILY_API_LIMIT},
        )
        safe_limit = quota.daily_limit * settings.TAG_COLLECTION_QUOTA_PERCENT // 100
        if quota.request_count + quota.reserved_count + 1 > safe_limit:
            return False
        quota.reserved_count += 1
        quota.save(update_fields=["reserved_count", "updated_at"])
    return True


def _settle_request(made, error):
    succeeded = error in {"", "insufficient_evidence"}
    ProviderQuotaUsage.objects.filter(
        provider="naver_search", usage_date=timezone.localdate(),
    ).update(
        reserved_count=F("reserved_count") - 1,
        request_count=F("request_count") + made,
        success_count=F("success_count") + (made if succeeded else 0),
        failed_count=F("failed_count") + (0 if succeeded else made),
        rate_limited_count=F("rate_limited_count") + (made if error == "rate_limited" else 0),
    )
