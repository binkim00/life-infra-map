import csv
import json
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import Place
from recommendations.services.kakao_place_matcher import address_tokens, normalize_address, normalize_name
from recommendations.services.map_search import calculate_distance_m


PUBLIC_SOURCES = {
    "parking": ("public_parking_standard",),
    "city_park": ("citypark_standard",),
    "tourism": ("tour_api",),
    "beach": ("beach_api",),
    "library": ("data_go_kr",),
}
MAX_DISTANCE_M = 250
GRID_SIZE = 0.002


class Command(BaseCommand):
    help = "Analyze public-source and Kakao Place duplicate candidates without merging or deleting Places."

    def add_arguments(self, parser):
        parser.add_argument("--category", action="append", choices=PUBLIC_SOURCES)
        parser.add_argument("--output", default="tmp/public_kakao_duplicate_report.json")
        parser.add_argument("--csv-output", default="tmp/public_kakao_duplicate_candidates.csv")
        parser.add_argument("--examples", type=int, default=20)

    def handle(self, *args, **options):
        categories = options["category"] or list(PUBLIC_SOURCES)
        report, rows = analyze_duplicates(categories, example_limit=max(1, options["examples"]))
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_output = Path(options["csv_output"]).resolve()
        csv_output.parent.mkdir(parents=True, exist_ok=True)
        with csv_output.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=(
                "status", "category", "public_place_id", "public_source", "public_name", "public_address",
                "kakao_place_id", "kakao_external_id", "kakao_name", "kakao_address",
                "distance_m", "name_similarity", "address_similarity", "region_match", "risk_reason",
            ))
            writer.writeheader()
            writer.writerows(rows)
        self.stdout.write(json.dumps({"output": str(output), "csv": str(csv_output), **report["summary"]}, ensure_ascii=False))


def analyze_duplicates(categories, *, example_limit=20):
    all_rows = []
    category_reports = {}
    for category in categories:
        public_places = list(Place.objects.filter(category=category, source__in=PUBLIC_SOURCES[category]).only(
            "id", "name", "address", "lat", "lng", "source", "external_id"
        ))
        kakao_places = list(Place.objects.filter(category=category, source="kakao_local").only(
            "id", "name", "address", "lat", "lng", "source", "external_id"
        ))
        grid = build_grid(kakao_places)
        candidate_places = high = ambiguous = 0
        category_rows = []
        for public in public_places:
            candidates = []
            for kakao in nearby(grid, public.lat, public.lng):
                assessment = assess_pair(public, kakao)
                if assessment["status"] != "unmatched":
                    candidates.append((kakao, assessment))
            candidates.sort(key=lambda item: (-item[1]["score"], item[1]["distance_m"]))
            if not candidates:
                continue
            candidate_places += 1
            high_candidates = [item for item in candidates if item[1]["status"] == "high_confidence"]
            if len(high_candidates) == 1:
                selected = high_candidates[0]
                status = "high_confidence"
                high += 1
            else:
                selected = candidates[0]
                status = "ambiguous"
                ambiguous += 1
            kakao, assessment = selected
            risk = assessment["risk_reason"]
            if len(candidates) > 1:
                risk = f"multiple_candidates={len(candidates)}; {risk}"
            category_rows.append(candidate_row(status, public, kakao, assessment, risk))
        all_rows.extend(category_rows)
        category_reports[category] = {
            "public_places": len(public_places),
            "kakao_places": len(kakao_places),
            "candidate_places": candidate_places,
            "high_confidence": high,
            "ambiguous": ambiguous,
            "examples": category_rows[:example_limit],
        }
    return {
        "summary": {
            "public_places": sum(row["public_places"] for row in category_reports.values()),
            "candidate_places": sum(row["candidate_places"] for row in category_reports.values()),
            "high_confidence": sum(row["high_confidence"] for row in category_reports.values()),
            "ambiguous": sum(row["ambiguous"] for row in category_reports.values()),
            "auto_merged": 0,
        },
        "categories": category_reports,
        "policy": {
            "max_distance_m": MAX_DISTANCE_M,
            "automatic_merge": False,
            "high_confidence_requires": "same category/region, exact name, <=50m, address support, and one clear candidate",
        },
    }, all_rows


def build_grid(places):
    grid = defaultdict(list)
    for place in places:
        grid[grid_key(place.lat, place.lng)].append(place)
    return grid


def nearby(grid, lat, lng):
    row, column = grid_key(lat, lng)
    for row_offset in (-1, 0, 1):
        for column_offset in (-1, 0, 1):
            yield from grid.get((row + row_offset, column + column_offset), ())


def grid_key(lat, lng):
    return int(float(lat) / GRID_SIZE), int(float(lng) / GRID_SIZE)


def assess_pair(public, kakao):
    distance = calculate_distance_m(public.lat, public.lng, kakao.lat, kakao.lng)
    if distance > MAX_DISTANCE_M:
        return {"status": "unmatched", "score": 0, "distance_m": distance}
    public_name = normalize_name(public.name)
    kakao_name = normalize_name(kakao.name)
    name_similarity = SequenceMatcher(None, public_name, kakao_name).ratio() if public_name and kakao_name else 0
    exact_name = public_name == kakao_name and bool(public_name)
    address_similarity = token_similarity(public.address, kakao.address)
    exact_address = normalize_address(public.address) == normalize_address(kakao.address) and bool(normalize_address(public.address))
    region_match = region_key(public.address) == region_key(kakao.address) and bool(region_key(public.address))
    score = (
        (50 if exact_name else 45 if name_similarity >= 0.9 else 35 if name_similarity >= 0.8 else 20 if name_similarity >= 0.7 else 0)
        + (30 if distance <= 20 else 25 if distance <= 50 else 18 if distance <= 100 else 10)
        + (20 if exact_address else 16 if address_similarity >= 0.6 else 8 if address_similarity >= 0.35 else 0)
        + (5 if region_match else -30)
    )
    high = exact_name and distance <= 50 and region_match and (exact_address or address_similarity >= 0.35)
    candidate = region_match and distance <= MAX_DISTANCE_M and (exact_name or name_similarity >= 0.75)
    status = "high_confidence" if high else "ambiguous" if candidate else "unmatched"
    risks = []
    if not exact_name:
        risks.append("name_not_exact")
    if not exact_address and address_similarity < 0.35:
        risks.append("weak_address")
    if distance > 50:
        risks.append("distance_over_50m")
    if not region_match:
        risks.append("region_mismatch")
    return {
        "status": status,
        "score": max(0, min(100, score)),
        "distance_m": distance,
        "name_similarity": round(name_similarity, 4),
        "address_similarity": round(address_similarity, 4),
        "region_match": region_match,
        "risk_reason": ",".join(risks) or "single exact candidate",
    }


def token_similarity(left, right):
    left_tokens = address_tokens(left)
    right_tokens = address_tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def region_key(address):
    tokens = str(address or "").split()
    return tuple(tokens[:2]) if len(tokens) >= 2 else tuple(tokens[:1])


def candidate_row(status, public, kakao, assessment, risk):
    return {
        "status": status,
        "category": public.category,
        "public_place_id": public.id,
        "public_source": public.source,
        "public_name": public.name,
        "public_address": public.address,
        "kakao_place_id": kakao.id,
        "kakao_external_id": kakao.external_id,
        "kakao_name": kakao.name,
        "kakao_address": kakao.address,
        "distance_m": assessment["distance_m"],
        "name_similarity": assessment["name_similarity"],
        "address_similarity": assessment["address_similarity"],
        "region_match": assessment["region_match"],
        "risk_reason": risk,
    }
