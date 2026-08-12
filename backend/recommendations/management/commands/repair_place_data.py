"""
임포트 과정에서 생긴 Place 데이터 오류를 바로잡습니다.

1. 카테고리 교정
   같은 카카오 장소가 여러 카테고리 시드에 들어 있으면 `(source, external_id)` 유니크 제약 때문에
   나중에 임포트된 쪽 카테고리가 남습니다. 광안리/송도/송정해수욕장이 `tourism`으로 저장된 이유입니다.
   장소명이 카테고리를 분명히 알려주는 경우에만 교정합니다.

2. 누락 해수욕장 적재
   `import_fixture_places`는 db_ready 파일에서 `place_candidates`만 저장하고 `external_places`는 건너뜁니다.
   그래서 카카오 매칭에 실패한 해수욕장(해운대 등)이 어느 쪽으로도 저장되지 않았습니다.
   원본 정제 파일에서 근처에 같은 장소가 없는 건만 채웁니다.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from recommendations.models import Place
from recommendations.services.map_search import calculate_distance_m


REPO_DIR = Path(__file__).resolve().parents[4]
BEACH_SOURCE = REPO_DIR / "ExData" / "Cleaned" / "beach_places.json"

# 장소명 끝이 카테고리를 확정해 주는 경우만 교정합니다.
# `부산시민공원 화장실`처럼 카테고리 단어가 중간에 있는 이름은 건드리지 않습니다.
NAME_SUFFIX_CATEGORY = (
    ("해수욕장", "beach"),
    ("해변", "beach"),
    ("주차장", "parking"),
    ("공원", "city_park"),
)
REPAIRABLE_CATEGORIES = {"beach", "city_park", "parking", "tourism"}

# 같은 해수욕장이 카카오 이름으로 이미 있으면 중복 저장하지 않습니다.
DUPLICATE_RADIUS_M = 500


def resolve_category_by_name(name):
    text = (name or "").strip()
    for suffix, category in NAME_SUFFIX_CATEGORY:
        if text.endswith(suffix):
            return category
    return ""


class Command(BaseCommand):
    help = "잘못 저장된 Place 카테고리를 교정하고 누락된 해수욕장을 채웁니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="저장하지 않고 바뀔 내용만 출력합니다.",
        )
        parser.add_argument(
            "--skip-category",
            action="store_true",
            help="카테고리 교정을 건너뜁니다.",
        )
        parser.add_argument(
            "--skip-beach",
            action="store_true",
            help="누락 해수욕장 적재를 건너뜁니다.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: 저장하지 않습니다."))

        if not options["skip_category"]:
            self.repair_categories(dry_run=dry_run)
        if not options["skip_beach"]:
            self.import_missing_beaches(dry_run=dry_run)

    def repair_categories(self, *, dry_run):
        self.stdout.write("\n[1] 카테고리 교정")
        targets = []
        for place in Place.objects.filter(category__in=REPAIRABLE_CATEGORIES).only(
            "id", "name", "category", "address"
        ):
            expected = resolve_category_by_name(place.name)
            if expected and expected != place.category:
                targets.append((place, expected))

        if not targets:
            self.stdout.write("  교정 대상 없음")
            return

        for place, expected in targets[:20]:
            self.stdout.write(
                f"  {place.name[:26]:28s} {place.category:10s} -> {expected:10s} {place.address[:26]}"
            )
        if len(targets) > 20:
            self.stdout.write(f"  ... 외 {len(targets) - 20}건")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"  총 {len(targets)}건 (저장 안 함)"))
            return

        with transaction.atomic():
            for place, expected in targets:
                place.category = expected
                place.save(update_fields=["category", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"  {len(targets)}건 교정 완료"))

    def import_missing_beaches(self, *, dry_run):
        self.stdout.write("\n[2] 누락 해수욕장 적재")
        if not BEACH_SOURCE.exists():
            self.stdout.write(self.style.ERROR(f"  원본 없음: {BEACH_SOURCE}"))
            return

        rows = json.loads(BEACH_SOURCE.read_text(encoding="utf-8"))
        existing = list(
            Place.objects.filter(category="beach").values("name", "lat", "lng")
        )
        existing_external_ids = set(
            Place.objects.filter(source="beach_api").values_list("external_id", flat=True)
        )

        created = []
        for row in rows:
            external_id = (row.get("external_id") or "").strip()
            lat, lng = row.get("lat"), row.get("lng")
            if not external_id or lat is None or lng is None:
                continue
            if external_id in existing_external_ids:
                continue
            # 카카오 이름으로 이미 저장된 같은 해수욕장이면 건너뜁니다.
            if any(
                calculate_distance_m(lat, lng, other["lat"], other["lng"]) <= DUPLICATE_RADIUS_M
                for other in existing
            ):
                continue
            created.append(row)

        if not created:
            self.stdout.write("  적재할 항목 없음")
            return

        busan = [r for r in created if "부산" in str(r.get("address", ""))]
        self.stdout.write(f"  적재 대상 {len(created)}건 (부산 {len(busan)}건)")
        for row in busan[:10]:
            self.stdout.write(f"    {row['name']:12s} {row['lat']:.5f},{row['lng']:.5f}  {row['address']}")

        if dry_run:
            self.stdout.write(self.style.WARNING("  (저장 안 함)"))
            return

        with transaction.atomic():
            for row in created:
                Place.objects.create(
                    name=(row.get("name") or "")[:200],
                    category="beach",
                    address=(row.get("address") or "")[:255],
                    lat=row["lat"],
                    lng=row["lng"],
                    source=(row.get("source") or "beach_api")[:50],
                    external_id=(row.get("external_id") or "")[:100],
                    source_name=(row.get("source_name") or "")[:100],
                    detail_location=(row.get("detail_location") or "")[:255],
                    data_quality_status=row.get("data_quality_status") or "candidate",
                    data_quality_score=row.get("data_quality_score") or 50,
                    raw=row.get("raw") or {},
                )
        self.stdout.write(self.style.SUCCESS(f"  {len(created)}건 적재 완료"))
