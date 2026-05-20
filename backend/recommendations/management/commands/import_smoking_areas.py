import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from recommendations.models import Place, Tag, PlaceTag


class Command(BaseCommand):
    help = "중복 제거된 흡연구역 JSON 데이터를 DB에 저장합니다."

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

        with open(data_path, "r", encoding="utf-8") as file:
            items = json.load(file)

        smoking_tag, _ = Tag.objects.get_or_create(
            name="흡연구역",
            defaults={
                "tag_type": "category",
                "description": "흡연 가능 장소를 나타내는 기본 카테고리 태그",
            },
        )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        tag_count = 0

        for item in items:
            lat = item.get("lat")
            lng = item.get("lng")

            # 현재 Place 모델은 lat/lng가 필수라서 좌표 없는 candidate는 일단 제외
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

            _, tag_created = PlaceTag.objects.get_or_create(
                place=place,
                tag=smoking_tag,
                source="external_data",
                defaults={
                    "status": "confirmed",
                    "confidence": item.get("data_quality_score", 80),
                    "evidence": "흡연구역 병합 정규화 데이터 기반",
                    "is_verified": True,
                },
            )

            if tag_created:
                tag_count += 1

            for tag_name in item.get("candidate_tags", []):
                if not tag_name:
                    continue

                tag, _ = Tag.objects.get_or_create(
                    name=tag_name,
                    defaults={
                        "tag_type": "recommendation",
                        "description": "원본 데이터에서 추출한 후보 태그",
                    },
                )

                _, place_tag_created = PlaceTag.objects.get_or_create(
                    place=place,
                    tag=tag,
                    source="external_data",
                    defaults={
                        "status": "candidate",
                        "confidence": 60,
                        "evidence": "원본 데이터 candidate_tags 기반",
                        "is_verified": False,
                    },
                )

                if place_tag_created:
                    tag_count += 1

            for tag_name in item.get("warning_tags", []):
                if not tag_name:
                    continue

                tag, _ = Tag.objects.get_or_create(
                    name=tag_name,
                    defaults={
                        "tag_type": "warning",
                        "description": "데이터 품질 확인이 필요한 경고 태그",
                    },
                )

                _, place_tag_created = PlaceTag.objects.get_or_create(
                    place=place,
                    tag=tag,
                    source="external_data",
                    defaults={
                        "status": "needs_verification",
                        "confidence": 50,
                        "evidence": "원본 데이터 warning_tags 기반",
                        "is_verified": False,
                    },
                )

                if place_tag_created:
                    tag_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"흡연구역 import 완료: 생성 {created_count}개, 수정 {updated_count}개, "
                f"좌표 없음 제외 {skipped_count}개, 태그 연결 생성 {tag_count}개"
            )
        )