from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from recommendations.models import ResearchAudit


class Command(BaseCommand):
    help = "Record safe, structured Codex collection progress for the admin UI."

    def add_arguments(self, parser):
        parser.add_argument("run_key")
        parser.add_argument("status", choices=("running", "failed"))
        parser.add_argument("stage", choices=("prepare", "research", "verify"))

    @transaction.atomic
    def handle(self, *args, **options):
        run, _ = ResearchAudit.objects.select_for_update().get_or_create(
            run_key=options["run_key"], defaults={"payload": {}},
        )
        payload = dict(run.payload or {})
        now = timezone.now().isoformat()
        payload.setdefault("started_at", now)
        payload["run_status"] = options["status"]
        payload["stage"] = options["stage"]
        payload["stage_history"] = [
            *(payload.get("stage_history") or []),
            {"stage": options["stage"], "status": options["status"], "at": now},
        ]
        if options["status"] == "failed":
            payload["finished_at"] = now
            payload["failure_summary"] = f"{options['stage']} 단계 실패. 서버 작업 로그를 확인해 주세요."
        run.payload = payload
        run.save(update_fields=["payload"])
        self.stdout.write(f"{run.run_key}: {options['status']} {options['stage']}")
