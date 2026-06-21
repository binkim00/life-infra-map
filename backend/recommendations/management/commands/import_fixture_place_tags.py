import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.models import Place, PlaceTag, Tag


BACKEND_DIR = Path(__file__).resolve().parents[3]
FIXTURES_TAGS_DIR = BACKEND_DIR / "recommendations" / "fixtures" / "tags"


PLACE_TAG_FILE_CONFIGS = {
    "beach": {
        "filename": "beach_place_tag_seed.json",
    },
    "park": {
        "filename": "park_place_tag_seed.json",
    },
    "parking": {
        "filename": "parking_place_tag_seed.json",
    },
    "shelter": {
        "filename": "shelter_place_tag_seed.json",
    },
    "toilet": {
        "filename": "toilet_place_tag_seed.json",
    },
    "tourism": {
        "filename": "tourist_spot_busan_place_tag_seed.json",
    },
}


CATEGORY_ALIASES = {
    "city_park": ["city_park", "citypark", "park"],
    "citypark": ["city_park", "citypark", "park"],
    "park": ["city_park", "citypark", "park"],
    "free_wifi": ["free_wifi", "freewifi"],
    "freewifi": ["free_wifi", "freewifi"],
    "tourist_spot": ["tourist_spot", "tourism"],
    "tourism": ["tourist_spot", "tourism"],
}


TAG_SOURCE_CHOICES = {choice[0] for choice in PlaceTag.TAG_SOURCE_CHOICES}
TAG_STATUS_CHOICES = {choice[0] for choice in PlaceTag.TAG_STATUS_CHOICES}
TAG_TYPE_CHOICES = {choice[0] for choice in Tag.TAG_TYPE_CHOICES}


class Command(BaseCommand):
    help = "fixtures/tags 안의 PlaceTag seed 데이터를 Tag, PlaceTag 테이블에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=list(PLACE_TAG_FILE_CONFIGS.keys()) + ["all"],
            nargs="+",
            default=["all"],
            help="특정 태그 seed만 import합니다. 예: --only beach toilet tourism",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DB에 최종 저장하지 않고 처리 결과만 확인합니다.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="테스트용으로 일부 row만 처리합니다.",
        )
        parser.add_argument(
            "--min-confidence",
            type=int,
            default=0,
            help="지정한 confidence 미만의 PlaceTag row는 제외합니다.",
        )
        parser.add_argument(
            "--create-missing-places",
            action="store_true",
            help=(
                "Place가 없을 때 seed row의 장소 정보로 최소 Place를 생성합니다. "
                "기본값은 생성하지 않고 스킵입니다."
            ),
        )

    def handle(self, *args, **options):
        selected_keys = options["only"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        min_confidence = options["min_confidence"]
        create_missing_places = options["create_missing_places"]

        if "all" in selected_keys:
            selected_keys = list(PLACE_TAG_FILE_CONFIGS.keys())

        total_input_rows = 0
        total_filtered_rows = 0
        total_created_tags = 0
        total_created_place_tags = 0
        total_updated_place_tags = 0
        total_created_missing_places = 0
        total_skipped_rows = 0
        total_missing_places = 0

        with transaction.atomic():
            for key in selected_keys:
                config = PLACE_TAG_FILE_CONFIGS[key]
                path = FIXTURES_TAGS_DIR / config["filename"]

                rows = read_json_rows(path)

                if limit is not None:
                    rows = rows[:limit]

                input_count = len(rows)

                rows = [
                    row
                    for row in rows
                    if normalize_confidence(row.get("confidence")) >= min_confidence
                ]

                total_input_rows += input_count
                total_filtered_rows += len(rows)

                result = import_rows(
                    rows=rows,
                    create_missing_places=create_missing_places,
                )

                total_created_tags += result["created_tags"]
                total_created_place_tags += result["created_place_tags"]
                total_updated_place_tags += result["updated_place_tags"]
                total_created_missing_places += result["created_missing_places"]
                total_skipped_rows += result["skipped_rows"]
                total_missing_places += result["missing_places"]

                self.stdout.write("")
                self.stdout.write(f"=== {key} ===")
                self.stdout.write(f"파일: {path}")
                self.stdout.write(f"입력 row: {input_count}개")
                self.stdout.write(f"confidence 필터 후 row: {len(rows)}개")
                self.stdout.write(f"태그 생성: {result['created_tags']}개")
                self.stdout.write(
                    f"PlaceTag 생성 {result['created_place_tags']}개, "
                    f"수정 {result['updated_place_tags']}개"
                )
                self.stdout.write(f"Place 없음: {result['missing_places']}개")
                self.stdout.write(f"스킵 row: {result['skipped_rows']}개")

                if result["created_missing_places"]:
                    self.stdout.write(
                        self.style.WARNING(
                            f"seed 기반 Place 생성: {result['created_missing_places']}개"
                        )
                    )

                if result["tag_source_counts"]:
                    self.stdout.write(f"source: {dict(result['tag_source_counts'])}")

                if result["status_counts"]:
                    self.stdout.write(f"status: {dict(result['status_counts'])}")

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "dry-run 모드라 실제 DB 변경사항은 저장하지 않았습니다."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "PlaceTag import 처리 완료: "
                f"입력 {total_input_rows}개, "
                f"필터 후 {total_filtered_rows}개, "
                f"Tag 생성 {total_created_tags}개, "
                f"PlaceTag 생성 {total_created_place_tags}개, "
                f"PlaceTag 수정 {total_updated_place_tags}개, "
                f"seed 기반 Place 생성 {total_created_missing_places}개, "
                f"Place 없음 {total_missing_places}개, "
                f"스킵 {total_skipped_rows}개"
            )
        )


def read_json_rows(path):
    if not path.exists():
        raise CommandError(f"파일을 찾을 수 없습니다: {path}")

    text = path.read_text(encoding="utf-8")

    if text.startswith("version https://git-lfs.github.com/spec/v1"):
        raise CommandError(
            f"Git LFS 실제 파일이 아니라 포인터 파일입니다: {path}\n"
            "git lfs pull 실행 후 다시 시도해 주세요."
        )

    data = json.loads(text)

    if not isinstance(data, list):
        raise CommandError(f"PlaceTag seed 파일은 list 구조여야 합니다: {path}")

    return data


def import_rows(rows, create_missing_places=False):
    created_tags = 0
    created_place_tags = 0
    updated_place_tags = 0
    created_missing_places = 0
    skipped_rows = 0
    missing_places = 0

    tag_source_counts = Counter()
    status_counts = Counter()

    for row in rows:
        parsed = build_place_tag_data(row)

        if not parsed["is_valid"]:
            skipped_rows += 1
            continue

        place = find_place(parsed)

        if place is None and create_missing_places:
            place = create_place_from_seed(parsed)
            created_missing_places += 1

        if place is None:
            missing_places += 1
            skipped_rows += 1
            continue

        tag, tag_created = Tag.objects.get_or_create(
            name=parsed["tag_name"],
            defaults={
                "tag_type": parsed["tag_type"],
                "description": make_tag_description(parsed),
            },
        )

        if tag_created:
            created_tags += 1

        _, place_tag_created = PlaceTag.objects.update_or_create(
            place=place,
            tag=tag,
            source=parsed["tag_source"],
            defaults={
                "status": parsed["status"],
                "confidence": parsed["confidence"],
                "evidence": parsed["evidence"],
                "is_verified": parsed["is_verified"],
            },
        )

        if place_tag_created:
            created_place_tags += 1
        else:
            updated_place_tags += 1

        tag_source_counts[parsed["tag_source"]] += 1
        status_counts[parsed["status"]] += 1

    return {
        "created_tags": created_tags,
        "created_place_tags": created_place_tags,
        "updated_place_tags": updated_place_tags,
        "created_missing_places": created_missing_places,
        "skipped_rows": skipped_rows,
        "missing_places": missing_places,
        "tag_source_counts": tag_source_counts,
        "status_counts": status_counts,
    }


def build_place_tag_data(row):
    place_source = clean_text(row.get("place_source"))
    place_external_id = clean_text(row.get("place_external_id"))
    place_name = clean_text(row.get("place_name"))
    category = clean_text(row.get("category"))
    address = clean_text(row.get("address"))

    lat = to_float(row.get("lat"))
    lng = to_float(row.get("lng"))

    tag_name = clean_text(row.get("tag_name"))
    tag_type = normalize_tag_type(row.get("tag_type"))
    tag_source = normalize_tag_source(row.get("source"))
    status = normalize_status(row.get("status"))
    confidence = normalize_confidence(row.get("confidence"))
    evidence = clean_text(row.get("evidence"))
    is_verified = bool(row.get("is_verified")) or status == "confirmed"

    raw = row.get("raw")
    if not isinstance(raw, dict):
        raw = row

    is_valid = bool(tag_name) and bool(place_name) and lat is not None and lng is not None

    return {
        "is_valid": is_valid,
        "place_source": place_source,
        "place_external_id": place_external_id,
        "place_name": place_name,
        "category": category,
        "address": address,
        "lat": lat,
        "lng": lng,
        "tag_name": tag_name,
        "tag_type": tag_type,
        "tag_source": tag_source,
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "is_verified": is_verified,
        "raw": raw,
    }


def find_place(parsed):
    place_source = parsed["place_source"]
    place_external_id = parsed["place_external_id"]

    if place_source and place_external_id:
        place = Place.objects.filter(
            source=place_source,
            external_id=place_external_id,
        ).first()

        if place:
            return place

    place_name = parsed["place_name"]
    lat = parsed["lat"]
    lng = parsed["lng"]

    if not place_name or lat is None or lng is None:
        return None

    lat_margin = 0.000001
    lng_margin = 0.000001

    query = Place.objects.filter(
        name=place_name,
        lat__gte=lat - lat_margin,
        lat__lte=lat + lat_margin,
        lng__gte=lng - lng_margin,
        lng__lte=lng + lng_margin,
    )

    category_candidates = get_category_candidates(parsed["category"])
    if category_candidates:
        category_matched_place = query.filter(category__in=category_candidates).first()
        if category_matched_place:
            return category_matched_place

    return query.first()


def create_place_from_seed(parsed):
    source = parsed["place_source"] or "place_tag_seed"
    external_id = parsed["place_external_id"]

    if not external_id:
        external_id = f"generated_{parsed['category']}_{parsed['place_name']}_{parsed['lat']}_{parsed['lng']}"

    place, _ = Place.objects.update_or_create(
        source=source[:50],
        external_id=external_id[:100],
        defaults={
            "name": parsed["place_name"],
            "category": parsed["category"] or "unknown",
            "address": parsed["address"],
            "lat": parsed["lat"],
            "lng": parsed["lng"],
            "source_name": "place_tag_seed",
            "detail_location": "",
            "data_quality_status": "candidate",
            "data_quality_score": 50,
            "raw": {
                "source_type": "created_from_place_tag_seed",
                "place_tag_seed_raw": parsed["raw"],
                "data_note": (
                    "PlaceTag seed import 중 기존 Place를 찾지 못해 seed row의 "
                    "최소 장소 정보로 생성한 Place입니다."
                ),
            },
        },
    )

    return place


def get_category_candidates(category):
    category = clean_text(category)

    if not category:
        return []

    return CATEGORY_ALIASES.get(category, [category])


def make_tag_description(parsed):
    if parsed["tag_type"] == "warning":
        return "추천 시 확인이 필요한 주의 태그입니다."

    if parsed["tag_source"] == "blog_search":
        return "블로그 검색 결과를 기반으로 생성한 추천 후보 태그입니다."

    if parsed["tag_source"] == "field_rule":
        return "원본 데이터 필드 기반으로 생성한 태그입니다."

    if parsed["tag_source"] == "category_rule":
        return "카테고리 또는 기본 규칙 기반으로 생성한 태그입니다."

    return "장소 추천과 필터에 사용하는 태그입니다."


def normalize_tag_type(value):
    value = clean_text(value) or "recommendation"

    if value not in TAG_TYPE_CHOICES:
        return "recommendation"

    return value


def normalize_tag_source(value):
    value = clean_text(value) or "external_data"

    if value not in TAG_SOURCE_CHOICES:
        return "external_data"

    return value


def normalize_status(value):
    value = clean_text(value) or "candidate"

    if value == "suggested":
        value = "candidate"

    if value not in TAG_STATUS_CHOICES:
        return "candidate"

    return value


def normalize_confidence(value):
    if value is None:
        return 50

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 50

    if 0 <= confidence <= 1:
        confidence *= 100

    return max(0, min(100, int(round(confidence))))


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