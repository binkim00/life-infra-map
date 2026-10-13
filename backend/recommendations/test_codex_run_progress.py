from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import ResearchAudit


class CodexRunProgressTests(TestCase):
    def test_progress_and_failure_share_one_audit_with_safe_stage_summary(self):
        key = "result-20260928T000000Z.json"
        for status, stage in (("running", "prepare"), ("running", "research"), ("failed", "research")):
            call_command("record_codex_run", key, status, stage, stdout=StringIO())
        self.assertEqual(ResearchAudit.objects.count(), 1)
        payload = ResearchAudit.objects.get(run_key=key).payload
        self.assertEqual(payload["run_status"], "failed")
        self.assertEqual([item["stage"] for item in payload["stage_history"]], ["prepare", "research", "research"])
        self.assertIn("research", payload["failure_summary"])
        self.assertIn("finished_at", payload)
