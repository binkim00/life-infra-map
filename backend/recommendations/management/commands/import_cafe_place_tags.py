import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.models import Place, PlaceTag, Tag


BACKEND_DIR = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    BACKEND_DIR
    / "recommendations"
    / "fixtures"
    / "tags"
    / "cafe_external_place_tags_seed.json"
)

TAG_SOURCE_CHOICES = {choice[0] for choice in PlaceTag.TAG_SOURCE_CHOICES}
TAG_STATUS_CHOICES = {choice[0] for choice in PlaceTag.TAG_STATUS_CHOICES}
TAG_TYPE_CHOICES = {choice[0] for choice in Tag.TAG_TYPE_CHOICES}


class Command(BaseCommand):
    help = "카페 외부 장소 태그 seed를 Place, Tag, PlaceTag 테이블에 저장합니다."

    def add_arguments(self, parser):
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
        dry_run = options["dry_run"]
        limit = options["limit"]
        min_confidence = options["min_confidence"]

        rows = read_json_rows(FIXTURE_PATH)

        if limit is not None:
            rows = rows[:limit]

        rows = [
            row
            for row in rows
            if normalize_confidence(row.get("confidence")) >= min_confidence
        ]

        grouped = group_rows_by_place(rows)

        self.stdout.write(f"파일: {FIXTURE_PATH}")
        self.stdout.write(f"입력 tag row: {len(rows)}개")
        self.stdout.write(f"카페 장소 수: {len(grouped)}개")
        self.stdout.write(f"min-confidence: {min_confidence}")

        if dry_run:
            tag_names = sorted({
                clean_text(row.get("tag_name"))
                for row in rows
                if clean_text(row.get("tag_name"))
            })

            self.stdout.write("")
            self.stdout.write(self.style.WARNING("[dry-run] DB에는 저장하지 않습니다."))
            self.stdout.write(f"생성/수정 대상 카페 Place: {len(grouped)}개")
            self.stdout.write(f"태그 종류: {len(tag_names)}개")
            self.stdout.write(f"태그 예시: {', '.join(tag_names[:20])}")
            return

        created_places = 0
        updated_places = 0
        created_tags = 0
        created_place_tags = 0
        updated_place_tags = 0
        skipped_rows = 0

        with transaction.atomic():
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

                for row in place_rows:
                    parsed_tag = build_tag_data(row)

                    if not parsed_tag["tag_name"]:
                        skipped_rows += 1
                        continue

                    tag, tag_created = Tag.objects.get_or_create(
                        name=parsed_tag["tag_name"],
                        defaults={
                            "tag_type": parsed_tag["tag_type"],
                            "description": parsed_tag["description"],
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
                            "is_verified": parsed_tag["status"] == "confirmed",
                        },
                    )

                    if place_tag_created:
                        created_place_tags += 1
                    else:
                        updated_place_tags += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "카페 PlaceTag import 완료: "
                f"Place 생성 {created_places}개, Place 수정 {updated_places}개, "
                f"Tag 생성 {created_tags}개, "
                f"PlaceTag 생성 {created_place_tags}개, PlaceTag 수정 {updated_place_tags}개, "
                f"스킵 {skipped_rows}개"
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
        raise CommandError("카페 태그 seed 파일은 list 구조여야 합니다.")

    return data


def group_rows_by_place(rows):
    grouped = defaultdict(list)

    for row in rows:
        source = clean_text(row.get("external_source")) or clean_text(row.get("source")) or "kakao_local"
        external_id = clean_text(row.get("external_id"))

        if not external_id:
            continue

        grouped[(source, external_id)].append(row)

    return grouped


def build_place_data(rows):
    first = rows[0]

    source = clean_text(first.get("external_source")) or clean_text(first.get("source")) or "kakao_local"
    external_id = clean_text(first.get("external_id"))
    name = clean_text(first.get("place_name")) or clean_text(first.get("name"))
    category = clean_text(first.get("category")) or "cafe"
    address = clean_text(first.get("address"))
    lat = to_float(first.get("lat"))
    lng = to_float(first.get("lng"))

    raw_items = []
    suggested_tags = []
    warning_tags = []
    display_tags = []

    max_confidence = 0
    max_blog_evidence_count = 0
    area_name = ""
    source_query = ""

    for row in rows:
        tag_name = clean_text(row.get("tag_name"))
        tag_type = normalize_tag_type(row.get("tag_type"))
        confidence = normalize_confidence(row.get("confidence"))

        max_confidence = max(max_confidence, confidence)

        raw = row.get("raw") or {}
        if isinstance(raw, dict):
            max_blog_evidence_count = max(
                max_blog_evidence_count,
                to_int(raw.get("blog_evidence_count"), default=0),
            )
            area_name = area_name or clean_text(raw.get("area_name"))
            source_query = source_query or clean_text(raw.get("source_query"))

        if tag_name:
            if tag_type == "warning":
                if tag_name not in warning_tags:
                    warning_tags.append(tag_name)
            else:
                if tag_name not in suggested_tags:
                    suggested_tags.append(tag_name)

            if tag_name not in display_tags:
                display_tags.append(tag_name)

        raw_items.append({
            "tag_name": tag_name,
            "tag_type": tag_type,
            "tag_source": normalize_tag_source(row.get("tag_source")),
            "status": normalize_status(row.get("status")),
            "confidence": confidence,
            "evidence": clean_text(row.get("evidence")),
            "raw": raw,
        })

    data_quality_score = calculate_data_quality_score(
        max_confidence=max_confidence,
        blog_evidence_count=max_blog_evidence_count,
        tag_count=len(display_tags),
        warning_count=len(warning_tags),
    )

    data_quality_status = "candidate"
    if data_quality_score < 60:
        data_quality_status = "needs_review"

    raw = {
        "source_type": "cafe_external_place_tags_seed",
        "external_source": source,
        "external_id": external_id,
        "original_category": extract_first_raw_value(rows, "original_category"),
        "phone": extract_first_raw_value(rows, "phone"),
        "place_url": extract_first_raw_value(rows, "place_url"),
        "area_name": area_name,
        "source_query": source_query,
        "blog_evidence_count": max_blog_evidence_count,
        "suggested_tags": suggested_tags,
        "display_tags": display_tags,
        "warning_tags": warning_tags,
        "tag_details": raw_items,
        "data_note": (
            "카카오 로컬 API 장소 후보와 네이버 블로그 검색 결과의 제목/요약 문구를 "
            "기반으로 생성한 카페 추천 태그 후보입니다. 실제 시설 여부를 확정한 검증 "
            "데이터가 아니므로 candidate 상태로 사용합니다."
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
        "source_name": "kakao_local + naver_blog_search",
        "detail_location": area_name,
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

    if tag_type == "warning":
        description = "카페 추천 시 주의 정보로 함께 표시할 태그 후보입니다."
    else:
        description = "카페 추천에 활용하는 블로그 검색 기반 태그 후보입니다."

    return {
        "tag_name": tag_name,
        "tag_type": tag_type,
        "tag_source": tag_source,
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "description": description,
    }


def extract_first_raw_value(rows, key):
    for row in rows:
        raw = row.get("raw") or {}
        if isinstance(raw, dict) and raw.get(key):
            return raw.get(key)
    return ""


def normalize_tag_type(value):
    value = clean_text(value) or "recommendation"

    if value not in TAG_TYPE_CHOICES:
        return "recommendation"

    return value


def normalize_tag_source(value):
    value = clean_text(value) or "blog_search"

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
        return 70

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 70

    if 0 <= confidence <= 1:
        confidence *= 100

    return max(0, min(100, int(round(confidence))))


def calculate_data_quality_score(max_confidence, blog_evidence_count, tag_count, warning_count):
    score = 50

    score += min(max_confidence * 0.3, 30)
    score += min(blog_evidence_count * 0.2, 15)
    score += min(tag_count * 2, 10)
    score -= min(warning_count * 4, 12)

    return max(0, min(100, int(round(score))))


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
