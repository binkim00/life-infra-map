"""Plan from a bounded primary-key page instead of scanning each stratum.

Address matching happens only on the page. This avoids unindexed regional
prefix scans and nested demand/candidate subqueries over the entire registry.
"""
import math
import time
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError
from django.db.models import Sum
from django.utils import timezone

from recommendations.models import (
    CollectionPlannerState, Place, PlaceTagCollectionJob, ProviderQuotaUsage,
    TagEnrichmentRequest,
)
from recommendations.services.adaptive_tag_collection import adaptive_planned_requests
from recommendations.services.bootstrap_priority import priority_context
from recommendations.services.collection_resources import PlannerDeadline, planner_transaction
from recommendations.services.place_tag_collection import requested_tags_for_category, planned_requests_for_category


def plan_bounded_jobs(*, cycle_date, place_limit, provider, mode, categories,
                      regions, dry_run, region_priority_weights=None):
    from recommendations.management.commands.plan_daily_tag_collection import weighted_region_selection

    result = {"places": 0, "planned_requests": 0, "covered_strata": 0,
              "scanned": 0, "candidates": 0, "deferred": False}
    started = time.monotonic()
    cap = min(max(0, int(place_limit)), max(1, settings.TAG_COLLECTION_REFILL_LIMIT))
    if not cap:
        return result
    if not dry_run:
        # Persist a first checkpoint independently of planning rollback so even
        # a first-page timeout can save a durable cooldown.
        CollectionPlannerState.objects.get_or_create(provider=provider)
    try:
        with planner_transaction():
            if dry_run:
                state = CollectionPlannerState.objects.filter(provider=provider).first() or CollectionPlannerState(provider=provider)
            else:
                state = CollectionPlannerState.objects.select_for_update(nowait=True).get(provider=provider)
            if state.next_attempt_at and state.next_attempt_at > timezone.now():
                result["deferred"] = True
                return result
            usage = ProviderQuotaUsage.objects.filter(provider=provider, usage_date=cycle_date).first()
            queued = PlaceTagCollectionJob.objects.filter(
                provider=provider, status__in=("queued", "retry"),
            ).aggregate(total=Sum("planned_requests"))["total"] or 0
            safe_limit = math.floor(settings.TAG_COLLECTION_DAILY_API_LIMIT * settings.TAG_COLLECTION_QUOTA_PERCENT / 100)
            budget = max(0, safe_limit - queued - (usage.request_count + usage.reserved_count if usage else 0))
            if not budget:
                result["deferred"] = True
                return result
            page = list(Place.objects.filter(id__gt=state.cursor).order_by("id").values(
                "id", "category", "address", "detail_location",
            )[:max(1, settings.TAG_COLLECTION_SCAN_PAGE)])
            result["scanned"] = len(page)
            # Demand is read as concrete IDs first. No nested Place subquery.
            demand_ids = list(TagEnrichmentRequest.objects.filter(status="queued").order_by(
                "-priority", "created_at", "id",
            ).values_list("place_id", flat=True)[:cap])
            demand = list(Place.objects.filter(id__in=demand_ids).values(
                "id", "category", "address", "detail_location",
            ))
            candidates = {}
            daily_contexts = list(PlaceTagCollectionJob.objects.filter(
                provider=provider, cycle_date=cycle_date,
            ).values_list("context__region", "context__category")[:settings.TAG_COLLECTION_DAILY_PLACE_LIMIT + 1])
            cap = min(cap, max(0, settings.TAG_COLLECTION_DAILY_PLACE_LIMIT - len(daily_contexts)))
            if not cap:
                return result
            region_counts = {region: sum(row[0] == region for row in daily_contexts)
                             for region, _ in regions}
            category_counts = {category: sum(row[1] == category for row in daily_contexts)
                               for category in categories}
            targets = {}
            if mode == "bootstrap" and region_priority_weights and sum(region_priority_weights.values()) > 0:
                total = sum(region_priority_weights.values())
                targets = {region: settings.TAG_COLLECTION_DAILY_PLACE_LIMIT * region_priority_weights.get(region, 0) // total
                           for region, _ in regions}
                for region, _ in regions:
                    if sum(targets.values()) >= settings.TAG_COLLECTION_DAILY_PLACE_LIMIT:
                        break
                    targets[region] += 1
            category_limit = math.ceil(settings.TAG_COLLECTION_DAILY_PLACE_LIMIT * max(
                settings.TAG_COLLECTION_BOOTSTRAP_CATEGORY_MAX_SHARE, 100 / max(1, len(categories))) / 100)
            cursor = state.cursor
            recent_cutoff = cycle_date - timedelta(days=settings.TAG_COLLECTION_REVISIT_DAYS)
            recent = set(PlaceTagCollectionJob.objects.filter(
                provider=provider, place_id__in=[row["id"] for row in page + demand],
                cycle_date__gte=recent_cutoff,
                status__in=("queued", "processing", "completed", "retry"),
            ).values_list("place_id", flat=True))

            def consider(row):
                if row["id"] in recent or row["category"] not in categories:
                    return
                if mode == "bootstrap" and category_counts[row["category"]] >= category_limit:
                    return
                for region, aliases in regions:
                    if targets and region_counts[region] >= targets[region]:
                        continue
                    if any((row["address"] or "").startswith(alias) or
                           (row["detail_location"] or "").startswith(alias) for alias in aliases):
                        candidates[row["id"]] = region
                        return

            # Reserve half the scoring pool for discovery, even under demand.
            for row in demand[:max(1, cap // 2)]:
                consider(row)
            for row in page:
                if len(candidates) >= cap * 3:
                    break
                consider(row)
                cursor = row["id"]
            if not page:
                cursor = 0
            places = list(Place.objects.filter(id__in=candidates).order_by("id"))
            result["candidates"] = len(places)
            contexts = priority_context(places, category_priorities=settings.TAG_COLLECTION_CATEGORY_PRIORITIES) if places else {}
            for place in places:
                contexts[place.id]["region"] = candidates[place.id]
            selected = weighted_region_selection(
                [(place, contexts[place.id]) for place in places], limit=cap,
                region_weights=region_priority_weights or {region: 1 for region, _ in regions},
            ) if places else []
            covered = set()
            for place, priority in selected:
                if time.monotonic() - started >= settings.TAG_COLLECTION_PLANNER_WALL_SECONDS:
                    # Roll back jobs AND cursor; no unprocessed page is skipped.
                    raise PlannerDeadline()
                region = priority["region"]
                if ((targets and region_counts[region] >= targets[region]) or
                        (mode == "bootstrap" and category_counts[place.category] >= category_limit)):
                    cursor = state.cursor
                    continue
                requests = (adaptive_planned_requests(priority["targeted_tags"]) if mode == "bootstrap"
                            else planned_requests_for_category(place.category))
                if result["planned_requests"] + requests > budget:
                    # Keep the page position so omitted candidates can be revisited.
                    cursor = state.cursor
                    break
                defaults = {"priority": max(1, priority["score"]),
                            "requested_tags": requested_tags_for_category(place.category),
                            "planned_requests": requests,
                            "context": {"mode": mode, "region": priority["region"],
                                        "category": place.category, "priority": priority,
                                        "adaptive": mode == "bootstrap",
                                        "targeted_tags": priority["targeted_tags"],
                                        "budget_bucket": priority["budget_bucket"],
                                        "source": "bounded_daily_plan"}}
                created = True
                if not dry_run:
                    _, created = PlaceTagCollectionJob.objects.get_or_create(
                        place=place, provider=provider, cycle_date=cycle_date,
                        defaults=defaults,
                    )
                if created:
                    result["places"] += 1
                    result["planned_requests"] += requests
                    covered.add((priority["region"], place.category))
                    region_counts[region] += 1
                    category_counts[place.category] += 1
            if result["places"] < len(candidates):
                # A selection/budget cap must not drop unselected candidate IDs.
                cursor = state.cursor
            if time.monotonic() - started >= settings.TAG_COLLECTION_PLANNER_WALL_SECONDS:
                raise PlannerDeadline()
            result["covered_strata"] = len(covered)
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            if not dry_run:
                state.cursor = cursor
                state.next_attempt_at = timezone.now() + timedelta(seconds=settings.TAG_COLLECTION_PLANNER_COOLDOWN_SECONDS)
                state.metrics = result
                state.save(update_fields=["cursor", "next_attempt_at", "metrics", "updated_at"])
            return result
    except (DatabaseError, PlannerDeadline) as exc:
        code = getattr(getattr(exc, "__cause__", None), "sqlstate", None)
        if isinstance(exc, DatabaseError) and code not in {"57014", "55P03"}:
            raise
        result.update(places=0, planned_requests=0, covered_strata=0, deferred=True)
        if code != "55P03":
            state = CollectionPlannerState.objects.filter(provider=provider).first()
            failures = min(5, int((state.metrics if state else {}).get("consecutive_deferrals", 0)) + 1)
            delay = min(900, settings.TAG_COLLECTION_PLANNER_COOLDOWN_SECONDS * (2 ** (failures - 1)))
            CollectionPlannerState.objects.filter(provider=provider).update(
                next_attempt_at=timezone.now() + timedelta(seconds=delay),
                metrics={"deferred": True, "reason": "planner_budget", "consecutive_deferrals": failures},
            )
        return result
