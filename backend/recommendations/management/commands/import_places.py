import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from recommendations.models import Place


BACKEND_DIR = Path(__file__).resolve().parents[3]
PROJECT_ROOT = BACKEND_DIR.parent

PLACE_FILE_CONFIGS = {
    "beach": {
        "path": "ExData/Cleaned/beach_places.json",
        "default_category": "beach",
        "default_source": "beach_public_data",
    },
    "citypark": {
        "path": "ExData/Cleaned/citypark_places.json",
        "default_category": "city_park",
        "default_source": "citypark_public_data",
    },
    "freewifi": {
        "path": "ExData/Cleaned/freewifi_places.json",
        "default_category": "free_wifi",
        "default_source": "freewifi_public_data",
    },
    "parking": {
        "path": "ExData/Cleaned/parking_places.json",
        "default_category": "parking",
        "default_source": "parking_public_data",
    },
    "shelter": {
        "path": "ExData/Cleaned/shelter_places.json",
        "default_category": "shelter",
        "default_source": "shelter_public_data",
    },
    "toilet": {
        "path": "ExData/Cleaned/toilet_places.json",
        "default_category": "toilet",
        "default_source": "toilet_public_data",
    },
    "tourism": {
        "path": "ExData/Cleaned/tourism_places.json",
        "default_category": "tourism",
        "default_source": "tourism_public_data",
    },
}

NAME_KEYS = [
    "name",
    "place_name",
    "title",
    "시설명",
    "장소명",
    "명칭",
    "주차장명",
    "공원명",
    "화장실명",
    "쉼터명",
    "와이파이명",
    "sta_nm",
    "content_title",
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
    "rdnmadr",
    "lnmadr",
]

LAT_KEYS = ["lat", "latitude", "위도", "y", "mapy"]
LNG_KEYS = ["lng", "lon", "longitude", "경도", "x", "mapx"]
EXTERNAL_ID_KEYS = [
    "external_id",
    "source_id",
    "place_external_id",
    "id",
    "contentid",
    "content_id",
    "관리번호",
    "번호",
    "num",
]
SOURCE_UPDATED_AT_KEYS = [
    "source_updated_at",
    "updated_at",
    "base_date",
    "기준일자",
    "데이터기준일자",
    "제공일자",
]
DETAIL_LOCATION_KEYS = [
    "detail_location",
    "상세위치",
    "설치장소상세",
    "설치장소",
    "위치상세",
]


class Command(BaseCommand):
    help = "정제된 장소 JSON 데이터를 Place 테이블에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=PLACE_FILE_CONFIGS.keys(),
            nargs="+",
            help="특정 카테고리만 import합니다. 예: --only parking toilet",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DB에 저장하지 않고 검증 결과만 출력합니다.",
        )

    def handle(self, *args, **options):
        selected_keys = options.get("only") or PLACE_FILE_CONFIGS.keys()
        dry_run = options.get("dry_run")

        total_created = 0
        total_updated = 0
        total_skipped = 0

        for config_key in selected_keys:
            config = PLACE_FILE_CONFIGS[config_key]
            path = PROJECT_ROOT / config["path"]

            items = read_json_items(path)

            created_count = 0
            updated_count = 0
            skipped_count = 0

            for item in items:
                parsed = build_place_data(item, config)

                if not parsed["is_valid"]:
                    skipped_count += 1
                    continue

                if dry_run:
                    continue

                _, created = Place.objects.update_or_create(
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
                        "raw": item,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            total_created += created_count
            total_updated += updated_count
            total_skipped += skipped_count

            self.stdout.write(
                self.style.SUCCESS(
                    f"[{config_key}] 처리 완료: 생성 {created_count}개, 수정 {updated_count}개, "
                    f"스킵 {skipped_count}개, 입력 {len(items)}개"
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run 모드라 DB에는 저장하지 않았습니다."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"전체 장소 import 완료: 생성 {total_created}개, 수정 {total_updated}개, 스킵 {total_skipped}개"
                )
            )


def read_json_items(path):
    if not path.exists():
        raise CommandError(f"파일을 찾을 수 없습니다: {path}")

    text = path.read_text(encoding="utf-8")

    if text.startswith("version https://git-lfs.github.com/spec/v1"):
        raise CommandError(
            f"Git LFS 실제 파일이 아니라 포인터 파일입니다: {path}\n"
            "git lfs pull 실행 후 다시 시도해 주세요."
        )

    data = json.loads(text)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["items", "data", "results", "places", "records"]:
            value = data.get(key)
            if isinstance(value, list):
                return value

    raise CommandError(f"지원하지 않는 JSON 구조입니다: {path}")


def build_place_data(item, config):
    name = clean_text(pick_first(item, NAME_KEYS))
    address = clean_text(pick_first(item, ADDRESS_KEYS))
    lat = to_float(pick_first(item, LAT_KEYS))
    lng = to_float(pick_first(item, LNG_KEYS))

    category = clean_text(item.get("category")) or config["default_category"]
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
        "source_name": clean_text(item.get("source_name")) or source,
        "source_updated_at": source_updated_at,
        "detail_location": detail_location,
        "data_quality_status": data_quality_status,
        "data_quality_score": data_quality_score,
    }


def pick_first(item, keys):
    for key in keys:
        value = item.get(key)
        if value not in [None, "", [], {}]:
            return value
    return None


def clean_text(value):
    if value is None:
        return ""

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
