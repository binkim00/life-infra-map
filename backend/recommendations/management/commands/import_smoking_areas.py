import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from recommendations.models import Place, Tag, PlaceTag


# Place.category만으로 이미 알 수 있는 기본 태그는 PlaceTag에 저장하지 않습니다.
BASIC_SMOKING_TAG_NAMES = [
    "흡연구역",
    "흡연",
    "흡연가능",
    "흡연장소",
    "생활편의",
]

# 흡연구역에서 추천/필터에 의미가 있는 세부 유형 태그만 저장합니다.
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
        "keywords": ["부스", "흡연부스", "smoking booth"],
    },
    "open": {
        "name": "개방형흡연구역",
        "confidence": 85,
        "keywords": ["개방", "개방형", "노천"],
    },
}

# 추천/필터 태그로 쓰기 애매한 메타데이터성 candidate_tags는 무시합니다.
IGNORED_CANDIDATE_PREFIXES = (
    "관리:",
    "상태:",
    "제보유형:",
)

# 원본 raw에서 시설 유형 판단에 사용할 수 있는 후보 컬럼입니다.
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
    help = "중복 제거된 흡연구역 JSON 데이터를 DB에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cleanup-basic-tags",
            action="store_true",
            help="기존에 저장된 흡연구역 기본 태그 PlaceTag를 삭제합니다.",
        )

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[3]
        data_path = (
            base_dir
            / "recommendations"
            / "fixtures"
            / "smoking_places_merged_deduplicated.json"
        )

        if not data_path.exists():
            self.stdout.write(
                self.style.ERROR(f"파일을 찾을 수 없습니다: {data_path}")
            )
            return

        if options.get("cleanup_basic_tags"):
            deleted_count = cleanup_basic_smoking_tags()
            self.stdout.write(
                self.style.WARNING(
                    f"기존 흡연구역 기본 태그 PlaceTag 삭제: {deleted_count}개"
                )
            )

        with open(data_path, "r", encoding="utf-8") as file:
            items = json.load(file)

        created_count = 0
        updated_count = 0
        skipped_count = 0
        detail_tag_count = 0

        for item in items:
            lat = item.get("lat")
            lng = item.get("lng")

            # 현재 Place 모델은 lat/lng가 필수라서 좌표 없는 candidate는 일단 제외합니다.
            if lat is None or lng is None:
                skipped_count += 1
                continue

            source_updated_at = None
            if item.get("source_updated_at"):
                source_updated_at = parse_date(str(item.get("source_updated_at")))

            place, created = Place.objects.update_or_create(
                source=item.get("source", ""),
                external_id=item.get("external_id", ""),
                defaults={
                    "name": item.get("name", "흡연구역"),
                    "category": item.get("category", "smoking_area"),
                    "address": item.get("address", ""),
                    "lat": lat,
                    "lng": lng,
                    "source_name": item.get("source_name", ""),
                    "source_updated_at": source_updated_at,
                    "detail_location": item.get("detail_location", ""),
                    "data_quality_status": item.get("data_quality_status", "candidate"),
                    "data_quality_score": item.get("data_quality_score", 50),
                    "raw": item.get("raw", {}),
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            detail_tags = extract_smoking_detail_tags(item)

            for detail_tag in detail_tags:
                tag, _ = Tag.objects.get_or_create(
                    name=detail_tag["name"],
                    defaults={
                        "tag_type": "recommendation",
                        "description": "흡연구역 원본 데이터에서 확인한 세부 유형 태그",
                    },
                )

                _, place_tag_created = PlaceTag.objects.update_or_create(
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

                if place_tag_created:
                    detail_tag_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"흡연구역 import 완료: 생성 {created_count}개, 수정 {updated_count}개, "
                f"좌표 없음 제외 {skipped_count}개, 세부 유형 태그 연결 생성 {detail_tag_count}개"
            )
        )


def cleanup_basic_smoking_tags():
    """
    기존 import 코드로 저장됐을 수 있는 기본 태그 PlaceTag를 삭제합니다.

    삭제 대상:
    - Place.category = smoking_area
    - Tag.name in BASIC_SMOKING_TAG_NAMES
    """
    deleted_count, _ = PlaceTag.objects.filter(
        place__category="smoking_area",
        tag__name__in=BASIC_SMOKING_TAG_NAMES,
    ).delete()

    return deleted_count


def extract_smoking_detail_tags(item):
    """
    Place.category만으로 알 수 있는 기본 태그는 저장하지 않습니다.

    저장하지 않는 예:
    - 흡연구역
    - 흡연
    - 흡연가능

    원본 데이터에서 명확히 판단 가능한 세부 유형만 PlaceTag로 저장합니다.

    저장 대상:
    - 실내흡연실
    - 실외흡연구역
    - 부스형흡연구역
    - 개방형흡연구역
    """
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
        matched_tags = match_smoking_detail_tags(text)

        for matched_tag in matched_tags:
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

    has_indoor = contains_any(
        normalized,
        SMOKING_DETAIL_TAG_RULES["indoor"]["keywords"],
    )
    has_outdoor = contains_any(
        normalized,
        SMOKING_DETAIL_TAG_RULES["outdoor"]["keywords"],
    )

    # "실내외"처럼 실내와 실외가 함께 등장하는 값은 어느 쪽으로도 확정하지 않습니다.
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


def clean_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in ["nan", "none", "null"]:
        return ""

    return value