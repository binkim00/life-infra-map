import hashlib
import json
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from recommendations.management.commands.promote_source_places import normalize_coordinates
from recommendations.models import (
    KakaoPlaceMatch,
    KakaoPlaceSearchCache,
    Place,
    SourcePlaceRecord,
)
from recommendations.services.kakao_local import search_places_by_keyword
from recommendations.services.kakao_place_matcher import (
    build_search_queries,
    candidate_snapshot,
    choose_match,
)


class ApiQuotaReached(Exception):
    pass


class Command(BaseCommand):
    help = "Match staged LOCALDATA/public records to canonical Kakao place IDs."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="localdata")
        parser.add_argument("--dataset", default="")
        parser.add_argument("--sido", default="")
        parser.add_argument("--category", default="")
        parser.add_argument(
            "--per-stratum",
            type=int,
            help="Select this many rows per --sido x --category cell.",
        )
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--radius", type=int, default=3000)
        parser.add_argument("--max-queries", type=int, default=2)
        parser.add_argument("--max-api-requests", type=int)
        parser.add_argument("--sleep", type=float, default=0)
        parser.add_argument("--confirmed-score", type=float, default=82)
        parser.add_argument("--min-margin", type=float, default=12)
        parser.add_argument("--cache-days", type=int, default=30)
        parser.add_argument("--match-statuses", default="")
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--refresh-cache", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")
        if options["max_api_requests"] is not None and options["max_api_requests"] < 1:
            raise CommandError("--max-api-requests must be at least 1.")
        if options["per_stratum"] is not None and options["per_stratum"] < 1:
            raise CommandError("--per-stratum must be at least 1.")

        sidos = [value.strip() for value in options["sido"].split(",") if value.strip()]
        categories = [
            value.strip() for value in options["category"].split(",") if value.strip()
        ]
        if options["per_stratum"] is not None and (not sidos or not categories):
            raise CommandError("--per-stratum requires --sido and --category lists.")

        queryset = SourcePlaceRecord.objects.filter(
            source=options["source"],
            is_active=True,
            id__gt=max(0, options["after_id"]),
        ).exclude(name="")
        if options["dataset"]:
            queryset = queryset.filter(dataset=options["dataset"])
        if sidos:
            queryset = queryset.filter(sido_name__in=sidos)
        if categories:
            queryset = queryset.filter(category__in=categories)

        statuses = {
            value.strip() for value in options["match_statuses"].split(",") if value.strip()
        }
        allowed_statuses = {choice[0] for choice in KakaoPlaceMatch.STATUS_CHOICES}
        if statuses - allowed_statuses:
            raise CommandError(
                "Unknown --match-statuses: " + ", ".join(sorted(statuses - allowed_statuses))
            )
        if statuses:
            queryset = queryset.filter(kakao_match__status__in=statuses)
        elif not options["refresh"]:
            queryset = queryset.filter(kakao_match__isnull=True)

        if options["per_stratum"] is not None:
            selected_ids = []
            for sido in sidos:
                for category in categories:
                    selected_ids.extend(queryset.filter(
                        sido_name=sido,
                        category=category,
                    ).order_by("id").values_list("id", flat=True)[:options["per_stratum"]])
            queryset = queryset.filter(id__in=selected_ids)

        queryset = queryset.order_by("sido_name", "category", "id")
        if options["limit"] is not None:
            queryset = queryset[:options["limit"]]

        stats = {
            "read": 0,
            "confirmed": 0,
            "ambiguous": 0,
            "unmatched": 0,
            "error": 0,
            "api_requests": 0,
            "cache_hits": 0,
            "last_id": options["after_id"],
            "quota_reached": False,
        }
        for record in queryset.iterator(chunk_size=max(1, options["batch_size"])):
            stats["read"] += 1
            stats["last_id"] = record.id
            try:
                outcome = match_source_record(
                    record,
                    stats=stats,
                    radius=max(1, min(options["radius"], 20000)),
                    max_queries=max(1, min(options["max_queries"], 3)),
                    max_api_requests=options["max_api_requests"],
                    sleep_seconds=max(0, options["sleep"]),
                    confirmed_score=max(0, min(options["confirmed_score"], 100)),
                    min_margin=max(0, options["min_margin"]),
                    cache_days=max(1, options["cache_days"]),
                    refresh_cache=options["refresh_cache"],
                    dry_run=options["dry_run"],
                )
                stats[outcome["status"]] += 1
            except ApiQuotaReached:
                stats["quota_reached"] = True
                stats["last_id"] = record.id - 1
                break
            except Exception as exc:
                stats["error"] += 1
                if not options["dry_run"]:
                    save_error(record, exc)
                self.stderr.write(f"record={record.id} error={exc.__class__.__name__}: {exc}")

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Kakao matching complete: read={stats['read']} "
            f"confirmed={stats['confirmed']} ambiguous={stats['ambiguous']} "
            f"unmatched={stats['unmatched']} error={stats['error']} "
            f"api_requests={stats['api_requests']} cache_hits={stats['cache_hits']} "
            f"last_id={stats['last_id']} quota_reached={stats['quota_reached']}"
        ))


def cache_key(query, lat, lng, radius, size):
    payload = json.dumps(
        {
            "query": query,
            "lat": round(lat, 5) if lat is not None else None,
            "lng": round(lng, 5) if lng is not None else None,
            "radius": radius,
            "size": size,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_search(
    query,
    *,
    lat,
    lng,
    radius,
    stats,
    max_api_requests=None,
    cache_days=30,
    refresh_cache=False,
    dry_run=False,
):
    size = 15
    key = cache_key(query, lat, lng, radius, size)
    now = timezone.now()
    cached = None
    if not refresh_cache:
        cached = KakaoPlaceSearchCache.objects.filter(
            query_hash=key,
            error_message="",
            expires_at__gt=now,
        ).first()
    if cached is not None:
        stats["cache_hits"] += 1
        return cached.response

    if max_api_requests is not None and stats["api_requests"] >= max_api_requests:
        raise ApiQuotaReached
    response = search_places_by_keyword(
        query,
        lat=lat,
        lng=lng,
        radius=radius,
        size=size,
    )
    stats["api_requests"] += 1
    if not dry_run:
        documents = response.get("documents") if isinstance(response, dict) else []
        KakaoPlaceSearchCache.objects.update_or_create(
            query_hash=key,
            defaults={
                "query": query,
                "lat": lat,
                "lng": lng,
                "radius": radius,
                "response": response if isinstance(response, dict) else {},
                "result_count": len(documents) if isinstance(documents, list) else 0,
                "error_message": "",
                "expires_at": now + timedelta(days=cache_days),
            },
        )
    return response


def match_source_record(
    record,
    *,
    stats,
    radius=3000,
    max_queries=2,
    max_api_requests=None,
    sleep_seconds=0,
    confirmed_score=82,
    min_margin=12,
    cache_days=30,
    refresh_cache=False,
    dry_run=False,
):
    coordinates = normalize_coordinates(
        record.source_x,
        record.source_y,
        record.coordinate_reference_system,
    )
    lat, lng = coordinates if coordinates else (None, None)
    candidates_by_id = {}
    used_query = ""
    outcome = {"status": "unmatched", "top": None, "margin": 0, "scored": []}

    for query in build_search_queries(record)[:max_queries]:
        used_query = query
        response = cached_search(
            query,
            lat=lat,
            lng=lng,
            radius=radius,
            stats=stats,
            max_api_requests=max_api_requests,
            cache_days=cache_days,
            refresh_cache=refresh_cache,
            dry_run=dry_run,
        )
        documents = response.get("documents", []) if isinstance(response, dict) else []
        for candidate in documents if isinstance(documents, list) else []:
            candidate_id = str(candidate.get("id") or "").strip()
            if candidate_id:
                candidates_by_id[candidate_id] = candidate
        outcome = choose_match(
            record,
            list(candidates_by_id.values()),
            source_coordinates=coordinates,
            confirmed_score=confirmed_score,
            min_margin=min_margin,
        )
        if outcome["status"] == "confirmed" and outcome["top"]["score"] >= 90:
            break
        if sleep_seconds:
            time.sleep(sleep_seconds)

    if not dry_run:
        persist_match(record, outcome, query=used_query)
    return outcome


@transaction.atomic
def persist_match(record, outcome, *, query):
    now = timezone.now()
    top = outcome.get("top")
    top_candidate = top["candidate"] if top else {}
    match, _ = KakaoPlaceMatch.objects.select_for_update().get_or_create(
        source_record=record,
    )
    preserve_confirmed = (
        match.status == "confirmed"
        and match.canonical_place_id is not None
        and outcome["status"] != "confirmed"
    )
    if preserve_confirmed:
        match.query = query[:500]
        match.candidates = [candidate_snapshot(item) for item in outcome.get("scored", [])[:10]]
        match.score_details = {
            "latest_outcome_status": outcome["status"],
            "latest_score": top["score"] if top else 0,
            "latest_score_margin": outcome.get("margin") or 0,
            "latest_details": top.get("details", {}) if top else {},
            "confirmed_match_preserved": True,
        }
        match.attempt_count += 1
        match.last_attempted_at = now
        match.error_message = ""
        match.save()
        return match
    match.status = outcome["status"]
    match.kakao_place_id = str(top_candidate.get("id") or "")[:100]
    match.score = top["score"] if top else 0
    match.score_margin = outcome.get("margin") or 0
    match.distance_m = top.get("distance_m") if top else None
    match.query = query[:500]
    match.score_details = top.get("details", {}) if top else {}
    match.candidates = [candidate_snapshot(item) for item in outcome.get("scored", [])[:10]]
    match.attempt_count += 1
    match.last_attempted_at = now
    match.error_message = ""

    if outcome["status"] == "confirmed":
        canonical = upsert_kakao_place(record, top_candidate, top["score"])
        match.canonical_place = canonical
        match.matched_at = now
        if record.normalized_place_id != canonical.id:
            record.normalized_place = canonical
            record.save(update_fields=["normalized_place", "updated_at"])
    match.save()
    return match


def upsert_kakao_place(record, candidate, score):
    try:
        lat = float(candidate.get("y"))
        lng = float(candidate.get("x"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Confirmed Kakao candidate has invalid coordinates.") from exc
    kakao_id = str(candidate.get("id") or "").strip()
    if not kakao_id:
        raise ValueError("Confirmed Kakao candidate has no place ID.")
    place, _ = Place.objects.update_or_create(
        source="kakao_local",
        external_id=kakao_id,
        defaults={
            "name": str(candidate.get("place_name") or record.name)[:200],
            "category": record.category if record.category != "food_service" else "restaurant",
            "address": str(candidate.get("road_address_name") or candidate.get("address_name") or "")[:255],
            "lat": lat,
            "lng": lng,
            "source_name": "Kakao Local API",
            "detail_location": str(candidate.get("road_address_name") or candidate.get("address_name") or "")[:255],
            "data_quality_status": "confirmed",
            "data_quality_score": int(round(score)),
            "raw": {
                "kakao_place_url": candidate.get("place_url") or "",
                "category_group_code": candidate.get("category_group_code") or "",
                "category_name": candidate.get("category_name") or "",
                "phone": candidate.get("phone") or "",
            },
        },
    )
    return place


def save_error(record, exc):
    now = timezone.now()
    match, _ = KakaoPlaceMatch.objects.get_or_create(source_record=record)
    if not (match.status == "confirmed" and match.canonical_place_id is not None):
        match.status = "error"
    match.error_message = f"{exc.__class__.__name__}: {exc}"[:2000]
    match.attempt_count += 1
    match.last_attempted_at = now
    match.save(update_fields=[
        "status", "error_message", "attempt_count", "last_attempted_at", "updated_at",
    ])
