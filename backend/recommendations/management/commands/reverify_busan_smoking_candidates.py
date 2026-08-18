import csv
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from .discover_busan_smoking_places import CANDIDATES, RETRIEVED_AT


EXCLUDED = {"EXISTING", "REJECTED"}


def reverification_reason(candidate):
    status = candidate["status"]
    if status == "HIGH_CONFIDENCE_WEB":
        return "최신 위치 서비스 확인은 유지되나 독립 공식·시설 Source를 추가 확보하지 못해 현 상태 유지"
    if status == "ASHTRAY_ONLY":
        return "재떨이 근거만 확인됨. 흡연 허용을 뜻하지 않아 permission unknown 유지"
    if status == "STALE":
        return "과거 정부 설치 기사는 명확하나 현행 터미널 안내에서 운영 위치를 확인하지 못함"
    if status == "POSSIBLY_REMOVED":
        return "최신 위치 페이지에 폐쇄 신고가 있고 현행 독립 근거가 없어 기본 지도 제외"
    if candidate["source_type"] == "official_contract":
        return "2026 설치 계약은 확인했지만 준공·개방·시설안내 근거를 추가 확보하지 못함"
    return "장소 식별 근거는 있으나 단일 웹 Source이고 현행 공식 근거를 추가 확보하지 못함"


class Command(BaseCommand):
    help = "Write a read-only focused reverification report for the 19 Busan candidates."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="tmp")

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for candidate in CANDIDATES:
            if candidate["status"] in EXCLUDED:
                continue
            permission = candidate["smoking_permission"]
            if candidate["status"] == "ASHTRAY_ONLY":
                permission = "unknown"
            verification = {
                "HIGH_CONFIDENCE_WEB": "WEB_VERIFIED",
                "ASHTRAY_ONLY": "ASHTRAY_ONLY",
                "STALE": "STALE",
                "POSSIBLY_REMOVED": "STALE",
            }.get(candidate["status"], "UNVERIFIED")
            rows.append({
                "name": candidate["candidate_name"],
                "previous_status": candidate["status"], "new_status": candidate["status"],
                "facility_type": candidate["facility_type"], "smoking_permission": permission,
                "verification_level": verification, "source": candidate["source_url"],
                "source_date": candidate["published_at"], "retrieved_at": RETRIEVED_AT,
                "evidence_span": candidate["evidence_span"],
                "confidence": candidate["evidence_confidence"], "db_action": "REPORT_ONLY",
                "reason": reverification_reason(candidate),
            })
        if len(rows) != 19:
            raise RuntimeError(f"Expected 19 focused candidates, got {len(rows)}")
        summary = dict(Counter(row["new_status"] for row in rows))
        payload = {"generated_at": RETRIEVED_AT, "dry_run": True, "database_writes": 0, "summary": summary, "rows": rows}
        (output_dir / "busan_smoking_candidate_reverification.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        fields = ["name", "previous_status", "new_status", "facility_type", "smoking_permission", "verification_level", "source", "source_date", "retrieved_at", "evidence_span", "confidence", "db_action", "reason"]
        with (output_dir / "busan_smoking_candidate_reverification.csv").open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False)))
