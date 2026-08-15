from collections import defaultdict

from django.conf import settings
from django.db.models import Case, Count, Q, Value, When
from django.db.models.fields import CharField
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence
from recommendations.services.place_tag_collection import COLLECTION_PROFILES, requested_tags_for_category


REGION_ALIASES = (
    ("서울특별시", ("서울특별시", "서울 ")),
    ("부산광역시", ("부산광역시", "부산 ")),
    ("대구광역시", ("대구광역시", "대구 ")),
    ("인천광역시", ("인천광역시", "인천 ")),
    ("광주광역시", ("광주광역시", "광주 ")),
    ("대전광역시", ("대전광역시", "대전 ")),
    ("울산광역시", ("울산광역시", "울산 ")),
    ("세종특별자치시", ("세종특별자치시", "세종 ")),
    ("경기도", ("경기도",)),
    ("강원특별자치도", ("강원특별자치도", "강원도")),
    ("충청북도", ("충청북도",)),
    ("충청남도", ("충청남도",)),
    ("전북특별자치도", ("전북특별자치도", "전라북도")),
    ("전라남도", ("전라남도",)),
    ("경상북도", ("경상북도",)),
    ("경상남도", ("경상남도",)),
    ("제주특별자치도", ("제주특별자치도", "제주도")),
)


def region_case(prefix=""):
    whens = []
    for region, aliases in REGION_ALIASES:
        condition = Q()
        for alias in aliases:
            condition |= Q(**{f"{prefix}address__startswith": alias})
            condition |= Q(**{f"{prefix}detail_location__startswith": alias})
        whens.append(When(condition, then=Value(region)))
    return Case(*whens, default=Value("기타"), output_field=CharField())


def build_coverage_report(*, now=None, thresholds=None):
    now = now or timezone.now()
    categories = tuple(COLLECTION_PROFILES)
    relevant_tags = {tag for category in categories for tag in requested_tags_for_category(category)}
    thresholds = thresholds or getattr(settings, "TAG_COLLECTION_READINESS_THRESHOLDS", {
        "evidence_coverage": 0.20,
        "tag_coverage": 0.10,
        "high_confidence": 0.40,
        "max_conflict": 0.10,
        "max_stale": 0.40,
    })

    totals = {
        (row["region"], row["category"]): row["count"]
        for row in Place.objects.filter(category__in=categories)
        .annotate(region=region_case())
        .values("region", "category")
        .annotate(count=Count("id"))
    }
    materialized = defaultdict(lambda: defaultdict(int))
    high_confidence = defaultdict(int)
    for row in (
        PlaceTag.objects.filter(place__category__in=categories, tag__name__in=relevant_tags)
        .annotate(region=region_case("place__"))
        .values("region", "place__category", "tag__name", "status")
        .annotate(count=Count("place_id", distinct=True), high=Count("place_id", distinct=True, filter=Q(confidence__gte=70)))
    ):
        key = (row["region"], row["place__category"], row["tag__name"])
        materialized[key][row["status"]] += row["count"]
        high_confidence[key] += row["high"]

    evidence_pairs = defaultdict(lambda: {"positive": set(), "negative": set(), "stale": set(), "sources": set()})
    for row in (
        PlaceTagEvidence.objects.filter(place__category__in=categories, tag__name__in=relevant_tags)
        .annotate(region=region_case("place__"))
        .values("region", "place__category", "tag__name", "place_id", "polarity", "source", "expires_at")
        .iterator(chunk_size=5000)
    ):
        key = (row["region"], row["place__category"], row["tag__name"])
        if row["expires_at"] and row["expires_at"] <= now:
            evidence_pairs[key]["stale"].add(row["place_id"])
            continue
        if row["polarity"] in {"positive", "negative"}:
            evidence_pairs[key][row["polarity"]].add(row["place_id"])
        evidence_pairs[key]["sources"].add(row["source"])

    cells = {}
    region_summary = defaultdict(lambda: {
        "total_places": 0, "evidence_places": set(), "possible_pairs": 0,
        "evidence_pairs": 0, "materialized": 0, "high": 0, "conflicts": 0,
        "stale_pairs": 0, "all_evidence_pairs": 0,
    })
    for (region, category), total in sorted(totals.items()):
        tag_rows = {}
        for tag_name in requested_tags_for_category(category):
            key = (region, category, tag_name)
            ev = evidence_pairs[key]
            active_places = ev["positive"] | ev["negative"]
            conflicts = ev["positive"] & ev["negative"]
            statuses = dict(materialized[key])
            tag_rows[tag_name] = {
                "evidence_coverage": ratio(len(active_places), total),
                "positive_places": len(ev["positive"]),
                "negative_places": len(ev["negative"]),
                "unknown_places": max(0, total - len(active_places)),
                "candidate": statuses.get("candidate", 0),
                "confirmed": statuses.get("confirmed", 0),
                "needs_verification": statuses.get("needs_verification", 0),
                "rejected": statuses.get("rejected", 0),
                "high_confidence": high_confidence[key],
                "conflict": len(conflicts),
                "stale": len(ev["stale"]),
                "source_diversity": len(ev["sources"]),
            }
            summary = region_summary[region]
            summary["evidence_places"].update(active_places)
            summary["possible_pairs"] += total
            summary["evidence_pairs"] += len(active_places)
            summary["materialized"] += sum(statuses.values())
            summary["high"] += high_confidence[key]
            summary["conflicts"] += len(conflicts)
            summary["stale_pairs"] += len(ev["stale"])
            summary["all_evidence_pairs"] += len(active_places | ev["stale"])
        cells[f"{region}/{category}"] = {"total_places": total, "tags": tag_rows}
        region_summary[region]["total_places"] += total

    regions = {}
    for region, summary in sorted(region_summary.items()):
        metrics = {
            "place_coverage": ratio(len(summary["evidence_places"]), summary["total_places"]),
            "tag_coverage": ratio(summary["evidence_pairs"], summary["possible_pairs"]),
            "high_confidence_ratio": ratio(summary["high"], summary["materialized"]),
            "conflict_ratio": ratio(summary["conflicts"], summary["evidence_pairs"]),
            "stale_ratio": ratio(summary["stale_pairs"], summary["all_evidence_pairs"]),
        }
        ready = (
            metrics["place_coverage"] >= thresholds["evidence_coverage"]
            and metrics["tag_coverage"] >= thresholds["tag_coverage"]
            and metrics["high_confidence_ratio"] >= thresholds["high_confidence"]
            and metrics["conflict_ratio"] <= thresholds["max_conflict"]
            and metrics["stale_ratio"] <= thresholds["max_stale"]
        )
        partial = metrics["place_coverage"] >= thresholds["evidence_coverage"] / 2
        regions[region] = {
            **metrics,
            "readiness": "READY" if ready else "PARTIAL" if partial else "NEEDS_ENRICHMENT",
            "total_places": summary["total_places"],
            "evidence_places": len(summary["evidence_places"]),
        }
    return {
        "generated_at": now.isoformat(),
        "thresholds": thresholds,
        "regions": regions,
        "cells": cells,
    }


def ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0
