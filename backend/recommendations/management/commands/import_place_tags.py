import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommendations.models import Place, PlaceTag, Tag


BACKEND_DIR = Path(__file__).resolve().parents[3]
PROJECT_ROOT = BACKEND_DIR.parent

TAG_FILE_CONFIGS = {
    "beach": {
        "path": "Test/apiTest/tag/beachTag/beach_place_tag_seed.json",
        "default_category": "beach",
        "default_place_source": "beach_public_data",
    },
    "parking": {
        "path": "Test/apiTest/tag/parkingTag/parking_place_tag_seed.json",
        "default_category": "parking",
        "default_place_source": "parking_public_data",
    },
    "park": {
        "path": "Test/apiTest/tag/parkTag/park_place_tag_seed.json",
        "default_category": "city_park",
        "default_place_source": "citypark_public_data",
    },
    "shelter": {
        "path": "Test/apiTest/tag/shelterTag/shelter_place_tag_seed.json",
        "default_category": "shelter",
        "default_place_source": "shelter_public_data",
    },
    "toilet": {
        "path": "Test/apiTest/tag/toiletTag/toilet_place_tag_seed.json",
        "default_category": "toilet",
        "default_place_source": "toilet_public_data",
    },
    "tourism": {
        "path": "Test/apiTest/tag/tourTag/tourist_spot_busan_place_tag_seed.json",
        "default_category": "tourism",
        "default_place_source": "tourism_public_data",
    },
}

TAG_SOURCE_CHOICES = {choice[0] for choice in PlaceTag.TAG_SOURCE_CHOICES}
TAG_STATUS_CHOICES = {choice[0] for choice in PlaceTag.TAG_STATUS_CHOICES}
TAG_TYPE_CHOICES = {choice[0] for choice in Tag.TAG_TYPE_CHOICES}

# Place.category만으로 이미 알 수 있거나, 정보 존재 여부에 가까운 태그는 기본적으로 import하지 않습니다.
DEFAULT_EXCLUDED_TAG_NAMES = {
    "주차장",
    "공원",
    "도시공원",
    "해수욕장",
    "바다",
    "공중화장실",
    "생활편의",
    "쉼터",
    "무료와이파이",
    "와이파이",
    "흡연구역",
    "흡연",
    "흡연가능",
    "무더위쉼터",
    "운영시간정보있음",
    "수용인원정보있음",
    "면적정보있음",
    "연락처있음",
}

PLACE_EXTERNAL_ID_KEYS = [
    "place_external_id",
    "external_id",
    "place_id",
    "source_id",
]
PLACE_SOURCE_KEYS = ["place_source", "source_place", "source"]
PLACE_NAME_KEYS = ["place_name", "name", "title", "장소명", "시설명"]
CATEGORY_KEYS = ["place_category", "category"]
LAT_KEYS = ["lat", "latitude", "위도", "mapy", "y"]
LNG_KEYS = ["lng", "lon", "longitude", "경도", "mapx", "x"]
TAG_NAME_KEYS = ["tag_name", "tag", "name"]
TAG_SOURCE_KEYS = ["tag_source", "source"]
TAG_STATUS_KEYS = ["status", "tag_status"]
TAG_TYPE_KEYS = ["tag_type", "type"]
CONFIDENCE_KEYS = ["confidence", "score"]
EVIDENCE_KEYS = ["evidence", "reason", "matched_keywords", "source_text"]


class Command(BaseCommand):
    help = "생성된 PlaceTag seed JSON 데이터를 DB에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=TAG_FILE_CONFIGS.keys(),
            nargs="+",
            help="특정 카테고리 태그만 import합니다. 예: --only parking toilet",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DB에 저장하지 않고 매칭 결과만 출력합니다.",
        )
        parser.add_argument(
            "--include-basic-tags",
            action="store_true",
            help="기본/노이즈 태그 제외 규칙을 적용하지 않습니다.",
        )

    def handle(self, *args, **options):
        selected_keys = options.get("only") or TAG_FILE_CONFIGS.keys()
        dry_run = options.get("dry_run")
        include_basic_tags = options.get("include_basic_tags")

        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_unmatched = 0

        for config_key in selected_keys:
            config = TAG_FILE_CONFIGS[config_key]
            path = PROJECT_ROOT / config["path"]
            items = read_json_items(path)

            created_count = 0
            updated_count = 0
            skipped_count = 0
            unmatched_count = 0

            for raw_item in items:
                for item in expand_tag_rows(raw_item):
                    parsed = build_tag_data(item, config)

                    if not parsed["tag_name"]:
                        skipped_count += 1
                        continue

                    if not include_basic_tags and parsed["tag_name"] in DEFAULT_EXCLUDED_TAG_NAMES:
                        skipped_count += 1
                        continue

                    place = find_place(parsed)

                    if place is None:
                        unmatched_count += 1
                        continue

                    if dry_run:
                        continue

                    tag, _ = Tag.objects.get_or_create(
                        name=parsed["tag_name"],
                        defaults={
                            "tag_type": parsed["tag_type"],
                            "description": parsed["description"],
                        },
                    )

                    _, created = PlaceTag.objects.update_or_create(
                        place=place,
                        tag=tag,
                        source=parsed["tag_source"],
                        defaults={
                            "status": parsed["status"],
                            "confidence": parsed["confidence"],
                            "evidence": parsed["evidence"],
                            "is_verified": parsed["status"] == "confirmed",
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

            total_created += created_count
            total_updated += updated_count
            total_skipped += skipped_count
            total_unmatched += unmatched_count

            self.stdout.write(
                self.style.SUCCESS(
                    f"[{config_key}] 태그 처리 완료: 생성 {created_count}개, 수정 {updated_count}개, "
                    f"스킵 {skipped_count}개, 장소 매칭 실패 {unmatched_count}개"
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run 모드라 DB에는 저장하지 않았습니다."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"전체 PlaceTag import 완료: 생성 {total_created}개, 수정 {total_updated}개, "
                    f"스킵 {total_skipped}개, 장소 매칭 실패 {total_unmatched}개"
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
        for key in ["items", "data", "results", "place_tags", "records"]:
            value = data.get(key)
            if isinstance(value, list):
                return value

    raise CommandError(f"지원하지 않는 JSON 구조입니다: {path}")


def expand_tag_rows(item):
    tag_name = clean_text(pick_first(item, TAG_NAME_KEYS))

    if tag_name:
        yield item
        return

    tags = item.get("tags")

    if not isinstance(tags, list):
        return

    for tag in tags:
        expanded = dict(item)
        expanded.pop("tags", None)

        if isinstance(tag, dict):
            expanded.update(tag)
        else:
            expanded["tag_name"] = tag

        yield expanded


def build_tag_data(item, config):
    tag_name = clean_text(pick_first(item, TAG_NAME_KEYS))
    tag_source = clean_text(pick_first(item, TAG_SOURCE_KEYS)) or "external_data"
    status = clean_text(pick_first(item, TAG_STATUS_KEYS)) or "candidate"
    tag_type = clean_text(pick_first(item, TAG_TYPE_KEYS)) or "recommendation"

    if tag_source not in TAG_SOURCE_CHOICES:
        if tag_source == "field_warning":
            tag_source = "warning_tags"
        else:
            tag_source = "external_data"

    if status not in TAG_STATUS_CHOICES:
        status = "candidate"

    if tag_type not in TAG_TYPE_CHOICES:
        tag_type = "recommendation"

    confidence = normalize_confidence(pick_first(item, CONFIDENCE_KEYS), status=status)
    evidence = stringify_evidence(pick_first(item, EVIDENCE_KEYS))

    return {
        "place_external_id": clean_text(pick_first(item, PLACE_EXTERNAL_ID_KEYS)),
        "place_source": clean_text(pick_first(item, PLACE_SOURCE_KEYS)) or config["default_place_source"],
        "place_name": clean_text(pick_first(item, PLACE_NAME_KEYS)),
        "category": clean_text(pick_first(item, CATEGORY_KEYS)) or config["default_category"],
        "lat": to_float(pick_first(item, LAT_KEYS)),
        "lng": to_float(pick_first(item, LNG_KEYS)),
        "tag_name": tag_name,
        "tag_source": tag_source,
        "status": status,
        "tag_type": tag_type,
        "confidence": confidence,
        "evidence": evidence,
        "description": f"{config['default_category']} 데이터 import 과정에서 생성된 태그",
    }


def find_place(parsed):
    place_external_id = parsed["place_external_id"]
    place_source = parsed["place_source"]

    if place_external_id:
        place = Place.objects.filter(
            source=place_source,
            external_id=place_external_id,
        ).first()

        if place:
            return place

        matches = list(Place.objects.filter(external_id=place_external_id)[:2])

        if len(matches) == 1:
            return matches[0]

    if parsed["place_name"] and parsed["lat"] is not None and parsed["lng"] is not None:
        place = (
            Place.objects.filter(
                category=parsed["category"],
                name=parsed["place_name"],
                lat__gte=parsed["lat"] - 0.00001,
                lat__lte=parsed["lat"] + 0.00001,
                lng__gte=parsed["lng"] - 0.00001,
                lng__lte=parsed["lng"] + 0.00001,
            )
            .order_by("id")
            .first()
        )

        if place:
            return place

    if parsed["place_name"]:
        matches = list(
            Place.objects.filter(
                category=parsed["category"],
                name=parsed["place_name"],
            )[:2]
        )

        if len(matches) == 1:
            return matches[0]

    return None


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


def normalize_confidence(value, status):
    if value is None:
        return 90 if status == "confirmed" else 70

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 70

    if 0 <= confidence <= 1:
        confidence *= 100

    return max(0, min(100, int(round(confidence))))


def stringify_evidence(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value[:1000]

    return json.dumps(value, ensure_ascii=False)[:1000]
