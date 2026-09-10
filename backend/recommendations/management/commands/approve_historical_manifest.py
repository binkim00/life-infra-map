"""Apply an explicitly reviewed, hash-pinned content manifest; never renew dates."""
import hashlib
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from recommendations.evidence_review_views import evidence_review, serialize
from recommendations.models import EvidenceReview, PlaceTag, PlaceTagEvidence
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


class Command(BaseCommand):
    help = "Preview hash-pinned historical content approvals; --apply requires a new backup file."

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--operator", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--simulate", action="store_true")
        parser.add_argument("--backup")

    def handle(self, *args, **options):
        plan = json.loads(Path(options["manifest"]).read_text(encoding="utf-8-sig"))
        items = plan.get("accepted", [])
        if not plan.get("run_key") or not 1 <= len(items) <= 10000 or len({x["id"] for x in items}) != len(items):
            raise CommandError("Invalid or oversized reviewed manifest")
        if options["apply"] and options["simulate"]:
            raise CommandError("Choose apply or simulate")
        if options["apply"] and not options["backup"]:
            raise CommandError("A new backup path is mandatory")
        actor = get_user_model().objects.get(username=options["operator"], is_staff=True, is_active=True)
        accepted, skipped, backup = [], [], []
        with transaction.atomic():
            with connection.cursor() as cursor:
                if not (options["apply"] or options["simulate"]) and connection.vendor == "postgresql":
                    cursor.execute("SET TRANSACTION READ ONLY")
                elif connection.vendor == "postgresql":
                    cursor.execute("SET LOCAL lock_timeout='5s'")
                    cursor.execute("SET LOCAL statement_timeout='60s'")
            for item in items:
                rows = PlaceTagEvidence.objects.select_related("place", "tag")
                if options["apply"] or options["simulate"]:
                    rows = rows.select_for_update(of=("self",))
                row = rows.get(pk=item["id"], source__in=WEB_EVIDENCE_SOURCES)
                state = serialize(row)
                if state["status"] != "pending":
                    skipped.append({"id": row.id, "reason": "already_reviewed"})
                    continue
                if state["freshness"] != "historical":
                    raise CommandError(f"Not historical: {row.id}")
                if (row.place_id != item["place_id"] or row.tag.name != item["tag"] or row.polarity != item["polarity"]
                        or str(row.updated_at) != item["observed_updated_at"]
                        or hashlib.sha256(row.evidence.encode()).hexdigest() != item["quote_hash"]):
                    raise CommandError(f"Manifest drift: {row.id}")
                accepted.append(row.id)
                backup.append({"id": row.id, "original": PlaceTagEvidence.objects.filter(pk=row.id).values().get(),
                               "reviews": list(EvidenceReview.objects.filter(evidence=row).values()),
                               "attestations": list(PlaceTagEvidence.objects.filter(evidence_key=f"admin-review:{row.id}").values()),
                               "tags": list(PlaceTag.objects.filter(place=row.place, tag=row.tag).values())})
            if options["apply"]:
                # Exclusive creation prevents destroying an earlier rollback snapshot.
                with Path(options["backup"]).open("x", encoding="utf-8") as handle:
                    json.dump({"run_key": plan["run_key"], "at": timezone.now(), "entries": backup}, handle, ensure_ascii=False, default=str)
            if options["apply"] or options["simulate"]:
                for pk in accepted:
                    note = (f"[사용자 위임 자동 내용 승인 {plan['run_key']}] 저장 인용문·상호·주소·극성 규칙 검토 결과. "
                            "과거 자료·현재 미확인. 원문 전체 재조회나 현장 확인이 아니며 필수 조건 충족 근거로 사용하지 않음. 원본·게시일·만료일 보존.")
                    request = APIRequestFactory().post("/admin/evidence/", {"status": "approved", "note": note}, format="json")
                    force_authenticate(request, actor)
                    response = evidence_review(request, pk)
                    if response.status_code != 200:
                        raise CommandError(f"Approval failed: {pk}, HTTP {response.status_code}")
            if options["simulate"]:
                transaction.set_rollback(True)
        persisted = EvidenceReview.objects.filter(evidence_id__in=accepted, status="approved").count()
        if options["apply"] and persisted != len(accepted):
            raise CommandError("Post-commit approval readback mismatch")
        self.stdout.write(json.dumps({"run_key": plan["run_key"], "mode": "apply" if options["apply"] else "simulate" if options["simulate"] else "preview",
                                      "eligible": len(accepted), "skipped": skipped, "persisted_approved": persisted, "ids": accepted}, ensure_ascii=False))
