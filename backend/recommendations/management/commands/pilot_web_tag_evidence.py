import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import save_place_candidate_evidence
from recommendations.models import Place, PlaceTag, PlaceTagCollectionJob, PlaceTagEvidence, ProviderQuotaUsage
from recommendations.services.web_tag_evidence_provider import (
    CATEGORY_TAGS,
    PROVIDER,
    collect_web_tag_evidence,
)


class Command(BaseCommand):
    help = "Run a cost-capped Busan Naver-to-Web evidence gap pilot."

    def add_arguments(self, parser):
        parser.add_argument("--cafe", type=int, default=100)
        parser.add_argument("--restaurant", type=int, default=100)
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--output-dir", default="tmp")

    def handle(self, *args, **options):
        counts = {"cafe": max(0, options["cafe"]), "restaurant": max(0, options["restaurant"])}
        selections = []
        allocation = Counter()
        for category, limit in counts.items():
            rows = select_pilot_places(category, limit, allocation)
            if len(rows) < limit:
                raise CommandError("Only {} eligible Busan {} places; {} requested.".format(len(rows), category, limit))
            selections.extend(rows)
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localdate().isoformat()
        baseline = snapshot(selections, source="naver_blog_search")
        report = {
            "generated_at": timezone.now().isoformat(),
            "region": "부산",
            "selection": selection_summary(selections),
            "naver_only_baseline": baseline,
            "pricing": {
                "web_search_tool_usd_per_call": 0.01,
                "total_cost_cap_usd": settings.WEB_EVIDENCE_SEARCH_MAX_COST_USD,
                "model": settings.WEB_EVIDENCE_SEARCH_MODEL,
            },
            "executed": bool(options["execute"]),
        }
        baseline_path = output_dir / "web_evidence_pilot_{}_baseline.json".format(stamp)
        baseline_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not options["execute"]:
            self.stdout.write(self.style.SUCCESS(
                "[dry-run] Busan web evidence pilot: cafe={} restaurant={} baseline={}".format(
                    counts["cafe"], counts["restaurant"], baseline_path
                )
            ))
            return
        if not settings.WEB_EVIDENCE_SEARCH_ENABLED:
            raise CommandError(
                "WEB_EVIDENCE_SEARCH_ENABLED is false; paid discovery remains disabled."
            )

        rows = []
        created_evidence = []
        failure_counts = Counter()
        tag_metrics = defaultdict(Counter)
        source_types = Counter()
        latencies = []
        place_tag_before = set(PlaceTag.objects.filter(
            place_id__in=[row["place"].id for row in selections],
            tag__name__in={row["tag"] for row in selections},
        ).values_list("place_id", "tag__name"))
        for selected in selections:
            place = selected["place"]
            tag = selected["tag"]
            result = collect_web_tag_evidence(place, [tag])
            if result.get("error") == "COST_OR_QUOTA_LIMIT":
                failure_counts[result["error"]] += 1
                break
            latencies.append(float(result.get("latency_ms") or 0))
            metric = tag_metrics[tag]
            metric["places_searched"] += 1
            metric["provider_calls"] += int(result.get("requests") or 0)
            metric["web_search_calls"] += int(result.get("web_search_calls") or 0)
            metric["results_checked"] += int(result.get("results_checked") or 0)
            metric["cost_micro_usd"] += round(float(result.get("cost_usd") or 0) * 1_000_000)
            evidences = result.get("evidences") or []
            if result.get("error"):
                failure_counts[result["error"]] += 1
            for evidence in evidences:
                observed_at = None
                if evidence.get("observed_date"):
                    observed_at = timezone.make_aware(datetime.fromisoformat(evidence["observed_date"]))
                saved, created = save_place_candidate_evidence(
                    place, evidence["tag_name"], evidence, observed_at=observed_at
                )
                is_active = saved.expires_at is None or saved.expires_at > timezone.now()
                metric["evidence"] += int(created)
                metric["active"] += int(created and is_active)
                metric["identity_pass"] += 1
                source_types[(evidence.get("raw") or {}).get("source_type") or "other"] += int(created)
                if created:
                    created_evidence.append(saved)
            PlaceTagCollectionJob.objects.update_or_create(
                place=place,
                provider=PROVIDER,
                cycle_date=timezone.localdate(),
                defaults={
                    "status": "completed",
                    "priority": selected["priority"],
                    "requested_tags": [tag],
                    "planned_requests": 1,
                    "attempt_count": 1,
                    "error_code": result.get("error") or "",
                    "stats": {
                        "requests": int(result.get("requests") or 0),
                        "web_search_calls": int(result.get("web_search_calls") or 0),
                        "results_checked": int(result.get("results_checked") or 0),
                        "evidences": len(evidences),
                        "new_evidences": sum(1 for row in created_evidence if row.place_id == place.id),
                        "latency_ms": result.get("latency_ms") or 0,
                        "cost_usd": result.get("cost_usd") or 0,
                        "failure_reasons": result.get("failure_reasons") or [],
                    },
                    "context": {
                        "region": "부산", "category": place.category,
                        "source": "web_evidence_pilot", "gap_tag": tag,
                    },
                },
            )
            rows.append({
                "place_id": place.id, "place": place.name, "address": place.address,
                "category": place.category, "tag": tag, "error": result.get("error") or "",
                "evidence": len(evidences), "latency_ms": result.get("latency_ms") or 0,
                "cost_usd": result.get("cost_usd") or 0,
            })

        after = snapshot(selections)
        place_tag_after = set(PlaceTag.objects.filter(
            place_id__in=[row["place"].id for row in selections],
            tag__name__in={row["tag"] for row in selections},
        ).values_list("place_id", "tag__name"))
        quota = ProviderQuotaUsage.objects.filter(
            provider=PROVIDER, usage_date=timezone.localdate()
        ).first()
        for tag, metric in tag_metrics.items():
            calls = metric["provider_calls"]
            active = metric["active"]
            metric["active_per_api"] = round(active / calls, 4) if calls else 0
            metric["cost_usd"] = round(metric.pop("cost_micro_usd") / 1_000_000, 8)
            metric["cost_per_active"] = round(metric["cost_usd"] / active, 8) if active else None
        report.update({
            "completed_at": timezone.now().isoformat(),
            "attempted_places": len(rows),
            "after": after,
            "incremental": {
                "evidence_places": len({row.place_id for row in created_evidence}),
                "evidence": len(created_evidence),
                "active_evidence": sum(
                    1 for row in created_evidence if row.expires_at is None or row.expires_at > timezone.now()
                ),
                "place_tags": len(place_tag_after - place_tag_before),
            },
            "tag_yield": {tag: dict(metric) for tag, metric in sorted(tag_metrics.items())},
            "failure_reasons": dict(failure_counts),
            "source_types": dict(source_types),
            "map_review_evidence": 0,
            "latency_ms": latency_summary(latencies),
            "provider": {
                "calls": quota.request_count if quota else 0,
                "success": quota.success_count if quota else 0,
                "failure": quota.failed_count if quota else 0,
                "metadata": quota.metadata if quota else {},
            },
            "expansion": {
                "executed": False,
                "reason": "A further 500 places require at least $5 in tool fees and exceed the total $5 task cap.",
            },
        })
        report_path = output_dir / "web_evidence_pilot_{}_result.json".format(stamp)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        review_path = output_dir / "web_evidence_pilot_{}_review.csv".format(stamp)
        write_review_csv(review_path, created_evidence[:30])
        self.stdout.write(self.style.SUCCESS(
            "Busan web evidence pilot: attempted={} new_evidence={} new_active={} cost=${} result={} review={}".format(
                len(rows), report["incremental"]["evidence"], report["incremental"]["active_evidence"],
                (quota.metadata or {}).get("estimated_cost_usd", 0) if quota else 0,
                report_path, review_path,
            )
        ))


def select_pilot_places(category, limit, allocation):
    targets = CATEGORY_TAGS[category]
    successful_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__diagnostics__identity_matches__gt=0,
    )
    no_tag_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__miss_reason="NO_TAG_EXPRESSION",
    )
    web_today = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider=PROVIDER, cycle_date=timezone.localdate(), status="completed"
    )
    candidates = list(Place.objects.filter(
        Q(address__startswith="부산") | Q(detail_location__startswith="부산"),
        category=category,
    ).annotate(
        naver_identity=Exists(successful_job),
        naver_no_tag=Exists(no_tag_job),
        web_done=Exists(web_today),
    ).filter(naver_identity=True, web_done=False).order_by("-naver_no_tag", "id")[:5000])
    active_rows = PlaceTagEvidence.objects.filter(
        place_id__in=[place.id for place in candidates], tag__name__in=targets, polarity="positive",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values_list(
        "place_id", "tag__name"
    )
    active = defaultdict(set)
    for place_id, tag in active_rows:
        active[place_id].add(tag)
    selected = []
    for place in candidates:
        missing = [tag for tag in targets if tag not in active[place.id]]
        if not missing:
            continue
        tag = min(missing, key=lambda value: (allocation[(category, value)], targets.index(value)))
        allocation[(category, tag)] += 1
        selected.append({
            "place": place,
            "tag": tag,
            "priority": 100 if place.naver_no_tag else 80,
            "reason": "naver_identity_no_tag" if place.naver_no_tag else "naver_identity_coverage_gap",
        })
        if len(selected) >= limit:
            break
    return selected


def snapshot(selections, source=None):
    place_ids = [row["place"].id for row in selections]
    tags = {row["tag"] for row in selections}
    evidence = PlaceTagEvidence.objects.filter(place_id__in=place_ids, tag__name__in=tags)
    if source:
        evidence = evidence.filter(source=source)
    active = evidence.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    tag_rows = {
        tag: {
            "evidence": evidence.filter(tag__name=tag).count(),
            "active": active.filter(tag__name=tag).count(),
            "active_places": active.filter(tag__name=tag).values("place_id").distinct().count(),
        }
        for tag in sorted(tags)
    }
    return {
        "evidence_places": evidence.values("place_id").distinct().count(),
        "active_evidence_places": active.values("place_id").distinct().count(),
        "evidence": evidence.count(),
        "active": active.count(),
        "place_tags": PlaceTag.objects.filter(place_id__in=place_ids, tag__name__in=tags).count(),
        "tags": tag_rows,
    }


def selection_summary(selections):
    categories = Counter(row["place"].category for row in selections)
    tags = Counter(row["tag"] for row in selections)
    reasons = Counter(row["reason"] for row in selections)
    return {"places": len(selections), "categories": dict(categories), "tags": dict(tags), "reasons": dict(reasons)}


def latency_summary(values):
    if not values:
        return {"average": 0, "median": 0, "max": 0}
    ordered = sorted(values)
    return {
        "average": round(sum(values) / len(values), 2),
        "median": round(ordered[len(ordered) // 2], 2),
        "max": round(max(values), 2),
    }


def write_review_csv(path, evidences):
    fields = [
        "place", "address", "category", "source_url", "title", "evidence_span", "tag",
        "polarity", "identity_confidence", "evidence_confidence", "identity_correct",
        "tag_supported", "polarity_correct", "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for evidence in evidences:
            writer.writerow({
                "place": evidence.place.name,
                "address": evidence.place.address,
                "category": evidence.place.category,
                "source_url": evidence.source_reference,
                "title": (evidence.context or {}).get("source_title", ""),
                "evidence_span": evidence.evidence,
                "tag": evidence.tag.name,
                "polarity": evidence.polarity,
                "identity_confidence": ((evidence.context or {}).get("identity") or {}).get("score", ""),
                "evidence_confidence": evidence.confidence,
                "identity_correct": "",
                "tag_supported": "",
                "polarity_correct": "",
                "notes": "",
            })
