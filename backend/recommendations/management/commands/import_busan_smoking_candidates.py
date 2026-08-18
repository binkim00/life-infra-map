import csv
import hashlib
import json
import math
from datetime import datetime, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag


COORDINATES = {
    "부산역 5번 출구 외부 흡연구역": (35.115642381974865, 129.0413831346399, "부산역 5번출구", "ENTRANCE"),
    "부산서부버스터미널 승강장 앞 흡연부스": (35.1632394721581, 128.982525426422, "부산서부버스터미널", "BUILDING"),
    "부산 중부소방서 흡연부스": (35.107105495206405, 129.03672882117422, "부산중부소방서", "BUILDING"),
    "어반풋볼파크 부산사상점 B구장 뒤 재떨이": (35.1647428388635, 128.978104227164, "어반풋볼파크 부산사상점", "BUILDING"),
    "광복동 패션거리 흡연구역": (35.0992950117855, 129.031306249087, "광복로패션거리", "LANDMARK"),
    "남포역 5번 출구 흡연구역": (35.098156201946985, 129.03515743460278, "남포역 5번 출구", "ENTRANCE"),
    "자갈치역 7번 출구 흡연구역": (35.0977397295328, 129.027745689388, "자갈치역 7번 출구", "ENTRANCE"),
    "롯데백화점 부산본점 옆 흡연구역": (35.15678954258721, 129.0564156583938, "롯데백화점 부산본점", "BUILDING"),
    "서면역 1번 출구 흡연구역": (35.1568528418017, 129.058948700726, "서면역 1번 출구", "ENTRANCE"),
    "센텀시티역 6번 출구 흡연구역": (35.1696132354844, 129.131855993602, "센텀시티역 6번 출구", "ENTRANCE"),
    "해운대역 3번 출구 흡연구역": (35.1634531787845, 129.159107172097, "해운대역 3번 출구", "ENTRANCE"),
    "부산대역 3번 출구 흡연구역": (35.2303199922452, 129.089161418186, "부산대역 3번 출구", "ENTRANCE"),
    "동래역 1번 출구 흡연구역": (35.20512361470795, 129.07818405317627, "동래역 1번 출구", "ENTRANCE"),
    "덕천역 3번 출구 흡연구역": (35.2098361901706, 129.0050231538111, "덕천역 3번 출구", "ENTRANCE"),
    "사상역 5번 출구 흡연구역": (35.16373033419587, 128.9838081318109, "사상역 5번 출구", "ENTRANCE"),
    "수영역 4번 출구 흡연구역": (35.167526346404706, 129.11468177614788, "수영역 4번 출구", "ENTRANCE"),
    "바른병원 인근 재떨이": (35.0976556079167, 129.025015507527, "바른병원", "BUILDING"),
    "바른빌딩 인근 재떨이": (35.097608605582614, 129.0248082024514, "바른빌딩", "BUILDING"),
    "한국전력 남부건설공사 인근 재떨이": (35.098623612899, 129.023820127248, "한국전력공사 남부건설본부", "BUILDING"),
}

TAG_BY_FACILITY = {
    "smoking_booth": "부스형흡연구역",
    "smoking_room": "실내흡연실",
    "ashtray_only": "재떨이위치",
    "designated_smoking_area": "흡연관련위치",
    "smoking_area_candidate": "흡연관련위치",
}

SOURCE_BY_TYPE = {
    "official_contract": "busan_smoking_government",
    "government_policy_article": "busan_smoking_government",
    "official_facility_operator": "busan_smoking_facility",
}


def _distance_m(a_lat, a_lng, b_lat, b_lng):
    y = math.radians(b_lat - a_lat)
    x = math.radians(b_lng - a_lng) * math.cos(math.radians((a_lat + b_lat) / 2))
    return math.sqrt(x * x + y * y) * 6371000


def _normalized(value):
    return "".join(character.lower() for character in (value or "") if character.isalnum())


def _external_id(source_url):
    return "busan-smoking-" + hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:24]


def _evidence_key(name, source_url):
    return "busan-smoking-" + hashlib.sha256(f"{name}|{source_url}".encode("utf-8")).hexdigest()[:40]


def _aware_date(value):
    try:
        parsed = datetime.strptime((value or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        parsed = timezone.localdate()
    # Noon avoids a date shift when API processes run in UTC while the report date
    # is a Korea-local calendar date.
    return timezone.make_aware(datetime.combine(parsed, time(hour=12)))


class Command(BaseCommand):
    help = "Idempotently import the 19 reviewed Busan smoking-related candidates."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--discovery", default="tmp/busan_smoking_facility_discovery.json")
        parser.add_argument("--reverification", default="tmp/busan_smoking_candidate_reverification.json")
        parser.add_argument("--output-dir", default="tmp")

    def handle(self, *args, **options):
        discovery_path = Path(options["discovery"])
        reverification_path = Path(options["reverification"])
        if not discovery_path.exists() or not reverification_path.exists():
            raise CommandError("Discovery and reverification JSON files are required.")
        discovered = json.loads(discovery_path.read_text(encoding="utf-8"))["candidates"]
        reviewed = {row["name"]: row for row in json.loads(reverification_path.read_text(encoding="utf-8"))["rows"]}
        candidates = [row for row in discovered if row["candidate_name"] in reviewed]
        if len(candidates) != 19 or set(COORDINATES) != set(reviewed):
            raise CommandError("The reviewed 19-candidate identity set does not match the coordinate manifest.")

        existing_queryset = Place.objects.filter(category="smoking_area")
        rows = []
        counters = {"insert": 0, "reuse": 0, "evidence_create": 0, "tag_create": 0, "failed": 0}
        with transaction.atomic():
            for candidate in candidates:
                name = candidate["candidate_name"]
                reviewed_row = reviewed[name]
                lat, lng, landmark, accuracy = COORDINATES[name]
                if not (34.8 <= lat <= 35.4 and 128.7 <= lng <= 129.35):
                    raise CommandError(f"Coordinate outside Busan bounds: {name}")
                source_url = candidate["source_url"]
                source = SOURCE_BY_TYPE.get(candidate["source_type"], "busan_smoking_web")
                external_id = _external_id(source_url)
                exact = existing_queryset.filter(source=source, external_id=external_id).first()
                nearby = []
                if not exact:
                    for place in existing_queryset.filter(lat__range=(lat - .001, lat + .001), lng__range=(lng - .001, lng + .001)):
                        distance = _distance_m(lat, lng, place.lat, place.lng)
                        if distance <= 30 and (_normalized(place.name) == _normalized(name) or (candidate["address"] and _normalized(place.address) == _normalized(candidate["address"]))):
                            nearby.append(place)
                place = exact or (nearby[0] if len(nearby) == 1 else None)
                action = "ALREADY_IMPORTED" if place and (place.raw or {}).get("import_batch") == "busan_smoking_candidates_2026_08" else ("REUSE" if place else "INSERT")
                location_description = candidate["location_description"]
                raw = {
                    "import_batch": "busan_smoking_candidates_2026_08",
                    "original_status": reviewed_row["previous_status"],
                    "verification_status": reviewed_row["new_status"],
                    "facility_type": candidate["facility_type"],
                    "smoking_permission": "unknown" if candidate["facility_type"] == "ashtray_only" else "unverified",
                    "location_description": location_description,
                    "location_landmark": landmark,
                    "location_directions": location_description,
                    "location_accuracy": accuracy,
                    "coordinate_source": "kakao_place_search",
                    "coordinate_accuracy": accuracy,
                    "coordinate_note": "흡연 설비 자체가 아닌 출구·건물·랜드마크 기준 좌표" if accuracy != "EXACT" else "설비 자체 좌표",
                    "location_source_url": source_url,
                    "location_evidence_span": candidate["evidence_span"],
                    "source_url": source_url,
                    "source_title": candidate["source_title"],
                    "source_type": candidate["source_type"],
                    "published_at": candidate["published_at"],
                    "retrieved_at": candidate["retrieved_at"],
                    "freshness": candidate["freshness"],
                }
                if options["apply"]:
                    if not place:
                        place = Place.objects.create(
                            name=name, category="smoking_area", address=candidate["address"],
                            lat=lat, lng=lng, source=source, external_id=external_id,
                            source_name=candidate["source_title"][:100],
                            source_updated_at=(datetime.strptime(candidate["published_at"][:10], "%Y-%m-%d").date() if candidate["published_at"] and len(candidate["published_at"]) >= 10 else None),
                            detail_location=location_description[:255],
                            data_quality_status="needs_review" if candidate["status"] not in {"HIGH_CONFIDENCE_WEB", "ASHTRAY_ONLY"} else "candidate",
                            data_quality_score=candidate["evidence_confidence"], raw=raw,
                        )
                        counters["insert"] += 1
                    else:
                        counters["reuse"] += 1
                    tag_name = TAG_BY_FACILITY[candidate["facility_type"]]
                    tag, _ = Tag.objects.get_or_create(name=tag_name, defaults={"tag_type": "warning" if tag_name == "재떨이위치" else "recommendation"})
                    place_tag, tag_created = PlaceTag.objects.update_or_create(
                        place=place, tag=tag, source="web_evidence",
                        defaults={"status": "needs_verification" if candidate["status"] in {"NEEDS_VERIFICATION", "STALE", "POSSIBLY_REMOVED"} else "candidate", "confidence": candidate["evidence_confidence"], "evidence": candidate["evidence_span"], "is_verified": False},
                    )
                    counters["tag_create"] += int(tag_created)
                    evidence, evidence_created = PlaceTagEvidence.objects.update_or_create(
                        evidence_key=_evidence_key(name, source_url),
                        defaults={
                            "place": place, "tag": tag, "source": candidate["source_type"],
                            "source_reference": source_url, "polarity": "negative" if candidate["status"] == "POSSIBLY_REMOVED" else "positive",
                            "confidence": candidate["evidence_confidence"], "evidence": candidate["evidence_span"],
                            "context": {**raw, "verification_status": candidate["status"]},
                            "raw": {"source_title": candidate["source_title"], "notes": candidate["notes"]},
                            "observed_at": _aware_date(candidate["retrieved_at"]),
                        },
                    )
                    counters["evidence_create"] += int(evidence_created)
                    place_id, evidence_id = place.id, evidence.id
                else:
                    counters["reuse" if place else "insert"] += 1
                    place_id, evidence_id = (place.id if place else None), None
                verification_level = {
                    "HIGH_CONFIDENCE_WEB": "WEB_VERIFIED",
                    "NEEDS_VERIFICATION": "UNVERIFIED",
                }.get(candidate["status"], candidate["status"])
                rows.append({
                    "candidate": name, "original_status": reviewed_row["previous_status"], "db_action": action,
                    "place_id": place_id, "final_name": name, "address": candidate["address"], "lat": lat, "lng": lng,
                    "coordinate_source": "kakao_place_search", "coordinate_accuracy": accuracy,
                    "location_description": location_description, "location_landmark": landmark,
                    "location_directions": location_description, "location_accuracy": accuracy,
                    "location_source_url": source_url, "location_evidence_span": candidate["evidence_span"],
                    "facility_type": candidate["facility_type"],
                    "smoking_permission": "unknown" if candidate["facility_type"] == "ashtray_only" else "unverified",
                    "verification_level": verification_level,
                    "default_visible": candidate["status"] not in {"STALE", "POSSIBLY_REMOVED"},
                    "evidence_id": evidence_id, "source_url": source_url,
                    "notes": reviewed_row["reason"],
                })
            if not options["apply"]:
                transaction.set_rollback(True)

        output_dir = Path(options["output_dir"]); output_dir.mkdir(parents=True, exist_ok=True)
        imported_count = Place.objects.filter(raw__import_batch="busan_smoking_candidates_2026_08").count() if options["apply"] else 0
        payload = {"applied": options["apply"], "counters": counters, "database_state": {"imported_places": imported_count}, "rows": rows}
        (output_dir / "busan_smoking_candidate_import_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        fields = list(rows[0])
        with (output_dir / "busan_smoking_candidate_import_result.csv").open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        self.stdout.write(self.style.SUCCESS(json.dumps(counters, ensure_ascii=False)))
