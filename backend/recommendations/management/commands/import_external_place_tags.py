import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.models import Place, PlaceTag, Tag


BACKEND_DIR = Path(__file__).resolve().parents[3]
FIXTURES_EXTERNAL_TAGS_DIR = (
    BACKEND_DIR
    / "recommendations"
    / "fixtures"
    / "tags"
    / "external"
)


EXTERNAL_TAG_FILE_CONFIGS = {
    "beach": {
        "filename": "beach_external_place_tags_seed.json",
    },
    "park": {
        "filename": "park_external_place_tags_seed.json",
    },
    "parking": {
        "filename": "parking_external_place_tags_seed.json",
    },
    "tourism": {
        "filename": "tourism_external_place_tags_seed.json",
    },
    "shelter": {
        "filename": "shelter_external_place_tags_seed.json",
    },
}


TAG_SOURCE_CHOICES = {choice[0] for choice in PlaceTag.TAG_SOURCE_CHOICES}
TAG_STATUS_CHOICES = {choice[0] for choice in PlaceTag.TAG_STATUS_CHOICES}
TAG_TYPE_CHOICES = {choice[0] for choice in Tag.TAG_TYPE_CHOICES}


class Command(BaseCommand):
    help = "external_places 기반 kakao_local PlaceTag seed를 Place, Tag, PlaceTag에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=list(EXTERNAL_TAG_FILE_CONFIGS.keys()) + ["all"],
            nargs="+",
            default=["all"],
            help="특정 external tag seed만 import합니다. 예: --only beach park parking",
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
            help="테스트용으로 일부 row만 처리합니다.",
        )
        parser.add_argument(
            "--min-confidence",
            type=int,
            default=0,
            help="지정한 confidence 미만의 태그는 제외합니다.",
        )

    def handle(self, *args, **options):
        selected_keys = options["only"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        min_confidence = options["min_confidence"]

        if "all" in selected_keys:
            selected_keys = list(EXTERNAL_TAG_FILE_CONFIGS.keys())

        total_input_rows = 0
        total_filtered_rows = 0
        total_created_places = 0
        total_updated_places = 0
        total_created_tags = 0
        total_created_place_tags = 0
        total_updated_place_tags = 0
        total_skipped_rows = 0

        with transaction.atomic():
            for key in selected_keys:
                config = EXTERNAL_TAG_FILE_CONFIGS[key]
                path = FIXTURES_EXTERNAL_TAGS_DIR / config["filename"]

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

                result = import_rows(rows)

                total_created_places += result["created_places"]
                total_updated_places += result["updated_places"]
                total_created_tags += result["created_tags"]
                total_created_place_tags += result["created_place_tags"]
                total_updated_place_tags += result["updated_place_tags"]
                total_skipped_rows += result["skipped_rows"]

                self.stdout.write("")
                self.stdout.write(f"=== {key} ===")
                self.stdout.write(f"파일: {path}")
                self.stdout.write(f"입력 row: {input_count}개")
                self.stdout.write(f"confidence 필터 후 row: {len(rows)}개")
                self.stdout.write(
                    f"Place 생성 {result['created_places']}개, 수정 {result['updated_places']}개"
                )
                self.stdout.write(f"Tag 생성: {result['created_tags']}개")
                self.stdout.write(
                    f"PlaceTag 생성 {result['created_place_tags']}개, "
                    f"수정 {result['updated_place_tags']}개"
                )
                self.stdout.write(f"스킵 row: {result['skipped_rows']}개")

                if result["tag_source_counts"]:
                    self.stdout.write(f"source: {dict(result['tag_source_counts'])}")

                if result["status_counts"]:
                    self.stdout.write(f"status: {dict(result['status_counts'])}")

                if result["category_counts"]:
                    self.stdout.write(f"category: {dict(result['category_counts'])}")

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
                "External PlaceTag import 처리 완료: "
                f"입력 {total_input_rows}개, "
                f"필터 후 {total_filtered_rows}개, "
                f"Place 생성 {total_created_places}개, "
                f"Place 수정 {total_updated_places}개, "
                f"Tag 생성 {total_created_tags}개, "
                f"PlaceTag 생성 {total_created_place_tags}개, "
                f"PlaceTag 수정 {total_updated_place_tags}개, "
                f"스킵 {total_skipped_rows}개"
            )
        )


def read_json_rows(path):
    if not path.exists():
        raise CommandError(
            f"파일을 찾을 수 없습니다: {path}\n"
            "먼저 python build_external_place_tag_seed.py 명령으로 external seed를 생성해 주세요."
        )

    text = path.read_text(encoding="utf-8")

    if text.startswith("version https://git-lfs.github.com/spec/v1"):
        raise CommandError(
            f"Git LFS 실제 파일이 아니라 포인터 파일입니다: {path}\n"
            "git lfs pull 실행 후 다시 시도해 주세요."
        )

    data = json.loads(text)

    if not isinstance(data, list):
        raise CommandError(f"external PlaceTag seed 파일은 list 구조여야 합니다: {path}")

    return data


def import_rows(rows):
    grouped = group_rows_by_external_place(rows)

    created_places = 0
    updated_places = 0
    created_tags = 0
    created_place_tags = 0
    updated_place_tags = 0
    skipped_rows = 0

    tag_source_counts = Counter()
    status_counts = Counter()
    category_counts = Counter()

    for place_key, place_rows in grouped.items():
        place_data = build_place_data(place_rows)

        if not place_data["is_valid"]:
            skipped_rows += len(place_rows)
            continue

        place, place_created = Place.objects.update_or_create(
            source=place_data["source"],
            external_id=place_data["external_id"],
            defaults={
                "name": place_data["name"],
                "category": place_data["category"],
                "address": place_data["address"],
                "lat": place_data["lat"],
                "lng": place_data["lng"],
                "source_name": place_data["source_name"],
                "detail_location": place_data["detail_location"],
                "data_quality_status": place_data["data_quality_status"],
                "data_quality_score": place_data["data_quality_score"],
                "raw": place_data["raw"],
            },
        )

        if place_created:
            created_places += 1
        else:
            updated_places += 1

        category_counts[place.category] += 1

        for row in place_rows:
            parsed_tag = build_tag_data(row)

            if not parsed_tag["tag_name"]:
                skipped_rows += 1
                continue

            tag, tag_created = Tag.objects.get_or_create(
                name=parsed_tag["tag_name"],
                defaults={
                    "tag_type": parsed_tag["tag_type"],
                    "description": make_tag_description(parsed_tag),
                },
            )

            if tag_created:
                created_tags += 1

            _, place_tag_created = PlaceTag.objects.update_or_create(
                place=place,
                tag=tag,
                source=parsed_tag["tag_source"],
                defaults={
                    "status": parsed_tag["status"],
                    "confidence": parsed_tag["confidence"],
                    "evidence": parsed_tag["evidence"],
                    "is_verified": parsed_tag["is_verified"],
                },
            )

            if place_tag_created:
                created_place_tags += 1
            else:
                updated_place_tags += 1

            tag_source_counts[parsed_tag["tag_source"]] += 1
            status_counts[parsed_tag["status"]] += 1

    return {
        "created_places": created_places,
        "updated_places": updated_places,
        "created_tags": created_tags,
        "created_place_tags": created_place_tags,
        "updated_place_tags": updated_place_tags,
        "skipped_rows": skipped_rows,
        "tag_source_counts": tag_source_counts,
        "status_counts": status_counts,
        "category_counts": category_counts,
    }


def group_rows_by_external_place(rows):
    grouped = defaultdict(list)

    for row in rows:
        source = clean_text(row.get("external_source")) or "kakao_local"
        external_id = clean_text(row.get("external_id"))

        if not external_id:
            continue

        grouped[(source, external_id)].append(row)

    return grouped


def build_place_data(rows):
    first = rows[0]

    source = clean_text(first.get("external_source")) or "kakao_local"
    external_id = clean_text(first.get("external_id"))
    name = clean_text(first.get("place_name")) or clean_text(first.get("name"))
    category = normalize_category(first.get("category"))
    address = clean_text(first.get("address"))
    lat = to_float(first.get("lat"))
    lng = to_float(first.get("lng"))

    raw_items = []
    display_tags = []
    warning_tags = []
    max_confidence = 0

    for row in rows:
        tag_name = clean_text(row.get("tag_name"))
        tag_type = normalize_tag_type(row.get("tag_type"))
        confidence = normalize_confidence(row.get("confidence"))

        max_confidence = max(max_confidence, confidence)

        if tag_name and tag_name not in display_tags:
            display_tags.append(tag_name)

        if tag_type == "warning" and tag_name and tag_name not in warning_tags:
            warning_tags.append(tag_name)

        raw_items.append({
            "tag_name": tag_name,
            "tag_type": tag_type,
            "tag_source": normalize_tag_source(row.get("tag_source")),
            "status": normalize_status(row.get("status")),
            "confidence": confidence,
            "evidence": clean_text(row.get("evidence")),
            "raw": row.get("raw", {}),
        })

    data_quality_score = calculate_data_quality_score(
        max_confidence=max_confidence,
        tag_count=len(display_tags),
        warning_count=len(warning_tags),
    )

    data_quality_status = "candidate"
    if data_quality_score < 60:
        data_quality_status = "needs_review"

    raw = {
        "source_type": "external_place_tags_seed",
        "external_source": source,
        "external_id": external_id,
        "display_tags": display_tags,
        "warning_tags": warning_tags,
        "tag_details": raw_items,
        "data_note": (
            "원본 데이터의 external_places에 매칭된 kakao_local 장소에 "
            "추천 태그 후보를 붙이기 위해 생성한 Place입니다."
        ),
    }

    return {
        "is_valid": bool(source and external_id and name and lat is not None and lng is not None),
        "source": source[:50],
        "external_id": external_id[:100],
        "name": name,
        "category": category,
        "address": address,
        "lat": lat,
        "lng": lng,
        "source_name": "kakao_local + external_place_tags",
        "detail_location": "",
        "data_quality_status": data_quality_status,
        "data_quality_score": data_quality_score,
        "raw": raw,
    }


def build_tag_data(row):
    tag_name = clean_text(row.get("tag_name"))
    tag_type = normalize_tag_type(row.get("tag_type"))
    tag_source = normalize_tag_source(row.get("tag_source"))
    status = normalize_status(row.get("status"))
    confidence = normalize_confidence(row.get("confidence"))
    evidence = clean_text(row.get("evidence"))
    is_verified = bool(row.get("is_verified")) or status == "confirmed"

    return {
        "tag_name": tag_name,
        "tag_type": tag_type,
        "tag_source": tag_source,
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "is_verified": is_verified,
    }


def normalize_category(value):
    value = clean_text(value) or "external_place"

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


def calculate_data_quality_score(max_confidence, tag_count, warning_count):
    score = 50
    score += min(max_confidence * 0.3, 30)
    score += min(tag_count * 2, 10)
    score -= min(warning_count * 4, 12)

    return max(0, min(100, int(round(score))))


def make_tag_description(parsed_tag):
    if parsed_tag["tag_type"] == "warning":
        return "추천 시 확인이 필요한 주의 태그입니다."

    if parsed_tag["tag_source"] == "blog_search":
        return "블로그 검색 결과를 기반으로 생성한 추천 후보 태그입니다."

    if parsed_tag["tag_source"] == "field_rule":
        return "원본 데이터 필드 기반으로 생성한 태그입니다."

    if parsed_tag["tag_source"] == "category_rule":
        return "카테고리 또는 기본 규칙 기반으로 생성한 태그입니다."

    return "장소 추천과 필터에 사용하는 태그입니다."


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
    except (TypeError, ValueError):
        return None