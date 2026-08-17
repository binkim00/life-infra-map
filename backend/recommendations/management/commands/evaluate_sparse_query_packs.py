import csv
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
from recommendations.services.bootstrap_priority import priority_context
from recommendations.services.evidence_scoring import parse_observed_date
from recommendations.services.place_tag_collection import (
    collect_naver_place_evidence,
    requested_tags_for_category,
)
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
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
        parser.add_argument("--allow-ai", action="store_true")
        parser.add_argument("--include-attempted", action="store_true")
        parser.add_argument("--validation-output", default="")
        parser.add_argument(
            "--pool", choices=("no_tag", "candidate", "stale"), default="no_tag"
        )
        parser.add_argument(
            "--packs",
            default="",
            help="Optional comma-separated pack names (discovery, work_sparse, solo, long_stay, talk).",
        )

    def handle(self, *args, **options):
        packs = [("discovery", None)] + list(FEATURE_QUERY_CLUSTERS)
        selected_packs = {
            value.strip() for value in options["packs"].split(",") if value.strip()
        }
        if selected_packs:
            known = {name for name, _ in packs}
            unknown = selected_packs - known
            if unknown:
                raise CommandError("Unknown query packs: " + ", ".join(sorted(unknown)))
            packs = [row for row in packs if row[0] in selected_packs]
        target_tags = tuple(dict.fromkeys(
            tag for pack_name, tags in packs if pack_name != "discovery" for tag in (tags or ())
        ))
        attempt_keys = [
            "{}:{}{}".format(
                options["pool"], pack_name, ":ai" if options["allow_ai"] else "",
            )
            for pack_name, _ in packs
        ]
        attempted_place_ids = set()
        if not options["include_attempted"]:
            for context, place_id in PlaceTagCollectionJob.objects.filter(
                provider="naver_search",
                context__targeted_attempts__isnull=False,
            ).values_list("context", "place_id"):
                attempts = (context or {}).get("targeted_attempts") or {}
                attempted_today = any(
                    str(value).startswith(str(timezone.localdate()))
                    for value in attempts.values()
                )
                if any(key in attempts for key in attempt_keys) or (
                    options["pool"] == "no_tag" and attempted_today
                ):
                    attempted_place_ids.add(place_id)
        hint_tags_by_place = {}
        if options["pool"] in {"candidate", "stale"}:
            target_tags = target_tags or FEATURE_QUERY_CLUSTERS[0][1]
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
            ).exclude(place_id__in=attempted_place_ids)
            for place_id, tag_name in place_ids_and_tags(hints, active_same_tag):
                if place_id not in attempted_place_ids:
                    hint_tags_by_place.setdefault(place_id, []).append(tag_name)
            place_ids = hint_tags_by_place
            candidate_places = list(Place.objects.filter(id__in=place_ids))
            priorities = priority_context(
                candidate_places,
                category_priorities=settings.TAG_COLLECTION_CATEGORY_PRIORITIES,
            )
            candidate_places.sort(
                key=lambda place: (-priorities[place.id]["score"], place.id),
            )
            jobs = (
                type("CandidateRow", (), {"place_id": place.id, "place": place})
                for place in candidate_places
            )
        else:
            jobs = PlaceTagCollectionJob.objects.filter(
                place__category=options["category"],
                place__address__startswith=options["region"],
                stats__miss_reason="NO_TAG_EXPRESSION",
                status="completed",
            ).exclude(place_id__in=attempted_place_ids).select_related("place").order_by("-id")
            if options["category"] == "restaurant":
                restaurant_jobs = list(jobs[:5000])
                restaurant_jobs.sort(
                    key=lambda job: restaurant_collection_quality(
                        job.place,
                        identity_misses=int((job.stats or {}).get("miss_reason") == "IDENTITY_MISMATCH"),
                        successful_jobs=int(bool((job.stats or {}).get("evidences"))),
                    )["score"],
                    reverse=True,
                )
                jobs = restaurant_jobs
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
        validation_rows = []
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
                        allow_ai=options["allow_ai"],
                    )
                else:
                    place_target_tags = pack_tags
                    if options["pool"] == "candidate":
                        place_target_tags = tuple(
                            tag for tag in pack_tags
                            if tag in hint_tags_by_place.get(place.id, ())
                        )
                        if not place_target_tags:
                            continue
                    result = collect_naver_place_evidence(
                        place,
                        requested_tags_for_category(place.category),
                        strategy="targeted_only",
                        targeted_tags=place_target_tags,
                        allow_ai=options["allow_ai"],
                    )
                made = min(1, int(result.get("requests") or 0))
                error = result.get("error") or ""
                _settle_request(made, error)
                stats["calls"] += made
                stats["places"] += 1
                stats["ai_calls"] += int(result.get("ai_calls") or 0)
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
                        if (evidence.get("extraction") or {}).get("method") == "ai":
                            validation_rows.append({
                                "place_id": place.id,
                                "place_name": place.name,
                                "address": place.address,
                                "category": place.category,
                                "tag": evidence["tag_name"],
                                "polarity": evidence["polarity"],
                                "evidence_span": (evidence.get("extraction") or {}).get("evidence_span", ""),
                                "source_title": evidence.get("source_title", ""),
                                "source_url": evidence.get("source_url", ""),
                                "identity_confidence": (evidence.get("identity") or {}).get("score", ""),
                                "review_notes": "",
                            })
                    record_targeted_attempt(
                        place,
                        "{}:{}{}".format(
                            options["pool"], pack_name, ":ai" if options["allow_ai"] else "",
                        ),
                        result,
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
        if options["validation_output"]:
            validation_path = Path(options["validation_output"]).resolve()
            validation_path.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = list(validation_rows[0]) if validation_rows else [
                "place_id", "place_name", "address", "category", "tag", "polarity",
                "evidence_span", "source_title", "source_url", "identity_confidence", "review_notes",
            ]
            with validation_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(validation_rows[:30])
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


def place_ids_and_tags(hints, active_same_tag):
    return hints.annotate(has_active=Exists(active_same_tag)).filter(
        has_active=False,
    ).values_list("place_id", "tag__name").distinct()


def record_targeted_attempt(place, attempt_key, result):
    cycle_date = timezone.localdate()
    job, created = PlaceTagCollectionJob.objects.get_or_create(
        place=place,
        provider="naver_search",
        cycle_date=cycle_date,
        defaults={
            "status": "completed",
            "priority": 1,
            "requested_tags": [],
            "planned_requests": max(1, int(result.get("requests") or 0)),
            "stats": {},
            "context": {"source": "targeted_evidence_validation"},
        },
    )
    context = dict(job.context or {})
    attempts = dict(context.get("targeted_attempts") or {})
    attempts[attempt_key] = timezone.now().isoformat()
    context["targeted_attempts"] = attempts
    job.context = context
    if created:
        job.status = "completed"
    job.save(update_fields=["context", "status", "updated_at"])
