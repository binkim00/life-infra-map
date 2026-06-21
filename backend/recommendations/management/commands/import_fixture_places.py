import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from recommendations.models import Place, PlaceTag, Tag


BACKEND_DIR = Path(__file__).resolve().parents[3]
FIXTURES_PLACES_DIR = BACKEND_DIR / "recommendations" / "fixtures" / "places"

PLACE_FILE_CONFIGS = {
    "beach": {
        "filename": "beach_db_ready.json",
        "kind": "db_ready",
        "default_category": "beach",
        "default_source": "beach_api",
    },
    "freewifi": {
        "filename": "freewifi_db_ready.json",
        "kind": "db_ready",
        "default_category": "freewifi",
        "default_source": "freewifi",
    },
    "shelter": {
        "filename": "shelter_db_ready.json",
        "kind": "db_ready",
        "default_category": "shelter",
        "default_source": "heat_shelter_api",
    },
    "toilet": {
        "filename": "toilet_db_ready.json",
        "kind": "db_ready",
        "default_category": "toilet",
        "default_source": "public_toilet_standard",
    },
    "smoking": {
        "filename": "smoking_places_merged_deduplicated.json",
        "kind": "plain_list",
        "default_category": "smoking_area",
        "default_source": "smokearea_kr_supabase",
    },
    "citypark": {
        "filename": "citypark_db_ready.json",
        "kind": "db_ready",
        "default_category": "city_park",
        "default_source": "citypark_standard",
    },
    "parking": {
        "filename": "parking_db_ready.json",
        "kind": "db_ready",
        "default_category": "parking",
        "default_source": "public_parking_standard",
    },
    "tourism": {
        "filename": "tourism_db_ready.json",
        "kind": "db_ready",
        "default_category": "tourism",
        "default_source": "tour_api",
    },
}

NAME_KEYS = [
    "name",
    "place_name",
    "title",
    "시설명",
    "장소명",
    "명칭",
]

ADDRESS_KEYS = [
    "address",
    "road_address",
    "jibun_address",
    "addr",
    "addr1",
    "addr2",
    "주소",
    "소재지도로명주소",
    "소재지지번주소",
    "소재지주소",
    "도로명주소",
    "지번주소",
]

LAT_KEYS = ["lat", "latitude", "위도", "y", "mapy"]
LNG_KEYS = ["lng", "lon", "longitude", "경도", "x", "mapx"]

EXTERNAL_ID_KEYS = [
    "source_id",
    "external_id",
    "place_external_id",
    "id",
    "contentid",
    "content_id",
]

SOURCE_UPDATED_AT_KEYS = [
    "source_updated_at",
    "updated_at",
    "base_date",
    "last_updated",
    "기준일자",
    "데이터기준일자",
    "제공일자",
]

DETAIL_LOCATION_KEYS = [
    "detail_location",
    "location_detail",
    "상세위치",
    "설치장소상세",
    "설치장소",
    "위치상세",
]

BASIC_SMOKING_TAG_NAMES = [
    "흡연구역",
    "흡연",
    "흡연가능",
    "흡연장소",
    "생활편의",
]

SMOKING_DETAIL_TAG_RULES = {
    "indoor": {
        "name": "실내흡연실",
        "confidence": 90,
        "keywords": ["실내", "실내형"],
    },
    "outdoor": {
        "name": "실외흡연구역",
        "confidence": 90,
        "keywords": ["실외", "옥외", "외부", "야외"],
    },
    "booth": {
        "name": "부스형흡연구역",
        "confidence": 85,
        "keywords": ["부스", "흡연부스", "smoking booth", "booth"],
    },
    "open": {
        "name": "개방형흡연구역",
        "confidence": 85,
        "keywords": ["개방", "개방형", "노천", "open-air"],
    },
}

IGNORED_CANDIDATE_PREFIXES = (
    "관리:",
    "상태:",
    "제보유형:",
)

RAW_FACILITY_KEYS = [
    "facility_type",
    "indoor_outdoor",
    "type",
    "시설형태",
    "시설유형",
    "흡연실 형태",
    "흡연실여부",
    "실내외구분",
    "실내실외",
    "구분",
    "설치형태",
]


class Command(BaseCommand):
    help = "fixtures/places 안의 최종 장소 데이터를 Place 테이블에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=list(PLACE_FILE_CONFIGS.keys()) + ["all"],
            nargs="+",
            default=["all"],
            help="특정 데이터만 import합니다. 예: --only beach toilet smoking",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DB에 저장하지 않고 처리 결과만 확인합니다.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="테스트용으로 일부 개수만 처리합니다.",
        )
        parser.add_argument(
            "--cleanup-basic-smoking-tags",
            action="store_true",
            help="기존에 저장된 흡연구역 기본 태그 PlaceTag를 삭제합니다.",
        )

    def handle(self, *args, **options):
        selected_keys = options["only"]
        dry_run = options["dry_run"]
        limit = options["limit"]

        if "all" in selected_keys:
            selected_keys = list(PLACE_FILE_CONFIGS.keys())

        if options["cleanup_basic_smoking_tags"] and not dry_run:
            deleted_count = cleanup_basic_smoking_tags()
            self.stdout.write(
                self.style.WARNING(
                    f"기존 흡연구역 기본 태그 PlaceTag 삭제: {deleted_count}개"
                )
            )

        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_external_skipped = 0
        total_smoking_detail_tags = 0

        for key in selected_keys:
            config = PLACE_FILE_CONFIGS[key]
            path = FIXTURES_PLACES_DIR / config["filename"]

            data = read_json(path)
            items, external_skipped = extract_items(data, config)

            if limit is not None:
                items = items[:limit]

            created_count = 0
            updated_count = 0
            skipped_count = 0
            smoking_detail_tag_count = 0

            self.stdout.write("")
            self.stdout.write(f"=== {key} ===")
            self.stdout.write(f"파일: {path}")
            self.stdout.write(f"입력 후보: {len(items)}개")
            self.stdout.write(f"external_places 스킵: {external_skipped}개")

            with transaction.atomic():
                for item in items:
                    parsed = build_place_data(item, config)

                    if not parsed["is_valid"]:
                        skipped_count += 1
                        continue

                    if dry_run:
                        continue

                    place, created = Place.objects.update_or_create(
                        source=parsed["source"],
                        external_id=parsed["external_id"],
                        defaults={
                            "name": parsed["name"],
                            "category": parsed["category"],
                            "address": parsed["address"],
                            "lat": parsed["lat"],
                            "lng": parsed["lng"],
                            "source_name": parsed["source_name"],
                            "source_updated_at": parsed["source_updated_at"],
                            "detail_location": parsed["detail_location"],
                            "data_quality_status": parsed["data_quality_status"],
                            "data_quality_score": parsed["data_quality_score"],
                            "raw": parsed["raw"],
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                    if parsed["category"] == "smoking_area":
                        smoking_detail_tag_count += save_smoking_detail_tags(place, item)

            total_created += created_count
            total_updated += updated_count
            total_skipped += skipped_count
            total_external_skipped += external_skipped
            total_smoking_detail_tags += smoking_detail_tag_count

            if dry_run:
                valid_count = len(items) - skipped_count
                self.stdout.write(
                    self.style.WARNING(
                        f"[dry-run] 저장 가능 {valid_count}개, 스킵 {skipped_count}개"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"생성 {created_count}개, 수정 {updated_count}개, "
                        f"스킵 {skipped_count}개, 흡연구역 세부 태그 생성 {smoking_detail_tag_count}개"
                    )
                )

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run 모드라 DB에는 저장하지 않았습니다."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"전체 장소 import 완료: 생성 {total_created}개, 수정 {total_updated}개, "
                    f"스킵 {total_skipped}개, external_places 스킵 {total_external_skipped}개, "
                    f"흡연구역 세부 태그 생성 {total_smoking_detail_tags}개"
                )
            )


def read_json(path):
    if not path.exists():
        raise CommandError(f"파일을 찾을 수 없습니다: {path}")

    text = path.read_text(encoding="utf-8")

    if text.startswith("version https://git-lfs.github.com/spec/v1"):
        raise CommandError(
            f"Git LFS 실제 파일이 아니라 포인터 파일입니다: {path}\n"
            "git lfs pull 실행 후 다시 시도해 주세요."
        )

    return json.loads(text)


def extract_items(data, config):
    kind = config["kind"]

    if kind == "db_ready":
        if not isinstance(data, dict):
            raise CommandError("db_ready 파일은 dict 구조여야 합니다.")

        place_candidates = data.get("place_candidates", [])
        external_places = data.get("external_places", [])

        if not isinstance(place_candidates, list):
            raise CommandError("place_candidates가 list 구조가 아닙니다.")

        return place_candidates, len(external_places) if isinstance(external_places, list) else 0

    if kind == "plain_list":
        if not isinstance(data, list):
            raise CommandError("plain_list 파일은 list 구조여야 합니다.")

        return data, 0

    raise CommandError(f"지원하지 않는 kind입니다: {kind}")


def build_place_data(item, config):
    name = clean_text(pick_first(item, NAME_KEYS))
    address = clean_text(pick_first(item, ADDRESS_KEYS))
    lat = to_float(pick_first(item, LAT_KEYS))
    lng = to_float(pick_first(item, LNG_KEYS))

    category = normalize_category(
        clean_text(item.get("category")) or config["default_category"],
        config["default_category"],
    )

    if config["kind"] == "db_ready":
        source = config["default_source"]
    else:
        source = clean_text(item.get("source")) or config["default_source"]

    source = source[:50]

    external_id = clean_text(pick_first(item, EXTERNAL_ID_KEYS))
    if not external_id:
        external_id = make_external_id(source, name, address, lat, lng)
    external_id = external_id[:100]

    source_updated_at = parse_source_date(pick_first(item, SOURCE_UPDATED_AT_KEYS))
    detail_location = clean_text(pick_first(item, DETAIL_LOCATION_KEYS))

    data_quality_status = clean_text(item.get("data_quality_status")) or "candidate"
    data_quality_score = to_int(item.get("data_quality_score"), default=50)

    source_name = clean_text(item.get("source_name")) or source

    raw = item.get("raw")
    if not isinstance(raw, dict):
        raw = item

    is_valid = bool(name) and is_valid_coordinate(lat, lng)

    return {
        "is_valid": is_valid,
        "name": name,
        "category": category,
        "address": address,
        "lat": lat,
        "lng": lng,
        "source": source,
        "external_id": external_id,
        "source_name": source_name,
        "source_updated_at": source_updated_at,
        "detail_location": detail_location,
        "data_quality_status": data_quality_status,
        "data_quality_score": data_quality_score,
        "raw": raw,
    }

def normalize_category(value, default_category):
    value = clean_text(value) or default_category

    category_map = {
        "citypark": "city_park",
        "park": "city_park",
        "city_park": "city_park",
        "tourist_spot": "tourism",
        "tourism": "tourism",
        "free_wifi": "freewifi",
        "freewifi": "freewifi",
    }

    return category_map.get(value, value)

def save_smoking_detail_tags(place, item):
    created_count = 0

    for detail_tag in extract_smoking_detail_tags(item):
        tag, _ = Tag.objects.get_or_create(
            name=detail_tag["name"],
            defaults={
                "tag_type": "recommendation",
                "description": "흡연구역 원본 데이터에서 확인한 세부 유형 태그",
            },
        )

        _, created = PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source="external_data",
            defaults={
                "status": "confirmed",
                "confidence": detail_tag["confidence"],
                "evidence": detail_tag["evidence"],
                "is_verified": True,
            },
        )

        if created:
            created_count += 1

    return created_count


def cleanup_basic_smoking_tags():
    deleted_count, _ = PlaceTag.objects.filter(
        place__category="smoking_area",
        tag__name__in=BASIC_SMOKING_TAG_NAMES,
    ).delete()

    return deleted_count


def extract_smoking_detail_tags(item):
    texts = []

    for tag_name in item.get("candidate_tags", []) or []:
        cleaned = clean_text(tag_name)

        if not cleaned:
            continue

        if cleaned in BASIC_SMOKING_TAG_NAMES:
            continue

        if cleaned.startswith(IGNORED_CANDIDATE_PREFIXES):
            continue

        texts.append(cleaned)

    raw = item.get("raw", {}) or {}

    if isinstance(raw, dict):
        for key in RAW_FACILITY_KEYS:
            value = clean_text(raw.get(key))

            if value:
                texts.append(value)

    detail_tags = []
    seen_names = set()

    for text in texts:
        for matched_tag in match_smoking_detail_tags(text):
            tag_name = matched_tag["name"]

            if tag_name in seen_names:
                continue

            seen_names.add(tag_name)
            detail_tags.append(
                {
                    "name": tag_name,
                    "confidence": matched_tag["confidence"],
                    "evidence": f"흡연구역 원본 세부 유형 정보 기반: {text}",
                }
            )

    return detail_tags


def match_smoking_detail_tags(text):
    normalized = clean_text(text).lower()

    if not normalized:
        return []

    matched = []

    has_indoor = contains_any(normalized, SMOKING_DETAIL_TAG_RULES["indoor"]["keywords"])
    has_outdoor = contains_any(normalized, SMOKING_DETAIL_TAG_RULES["outdoor"]["keywords"])

    if has_indoor and not has_outdoor:
        matched.append(
            {
                "name": SMOKING_DETAIL_TAG_RULES["indoor"]["name"],
                "confidence": SMOKING_DETAIL_TAG_RULES["indoor"]["confidence"],
            }
        )

    if has_outdoor and not has_indoor:
        matched.append(
            {
                "name": SMOKING_DETAIL_TAG_RULES["outdoor"]["name"],
                "confidence": SMOKING_DETAIL_TAG_RULES["outdoor"]["confidence"],
            }
        )

    for rule_key in ["booth", "open"]:
        rule = SMOKING_DETAIL_TAG_RULES[rule_key]

        if contains_any(normalized, rule["keywords"]):
            matched.append(
                {
                    "name": rule["name"],
                    "confidence": rule["confidence"],
                }
            )

    return matched


def contains_any(text, keywords):
    return any(str(keyword).lower() in text for keyword in keywords)


def pick_first(item, keys):
    for key in keys:
        value = item.get(key)

        if value not in [None, "", [], {}]:
            return value

    return None


def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, dict):
        for key in ["ko", "name", "title", "value"]:
            if value.get(key):
                return clean_text(value.get(key))

        return json.dumps(value, ensure_ascii=False)

    value = str(value).strip()

    if value.lower() in ["nan", "none", "null"]:
        return ""

    return value


def to_float(value):
    if value is None:
        return None

    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_source_date(value):
    value = clean_text(value)

    if not value:
        return None

    if len(value) == 8 and value.isdigit():
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"

    return parse_date(value)


def is_valid_coordinate(lat, lng):
    if lat is None or lng is None:
        return False

    return -90 <= lat <= 90 and -180 <= lng <= 180


def make_external_id(source, name, address, lat, lng):
    raw_key = f"{source}|{name}|{address}|{lat}|{lng}"
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:16]
    return f"generated_{digest}"
