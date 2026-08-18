import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommendations.services.codex_web_evidence_validator import validate_candidate


class Command(BaseCommand):
    help = "Validate Codex-researched web evidence candidates without paid search calls."

    def add_arguments(self, parser):
        parser.add_argument("input")
        parser.add_argument("--dry-run", action="store_true", default=True)

    def handle(self, *args, **options):
        path = Path(options["input"])
        if not path.exists():
            raise CommandError("Input file does not exist: {}".format(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CommandError("Input must be a list or an object with a results list.")
        counts = Counter()
        reasons = Counter()
        for row in rows:
            result = validate_candidate(row)
            counts[result["status"]] += 1
            if result["reason"]:
                reasons[result["reason"]] += 1
        self.stdout.write(json.dumps({
            "dry_run": True,
            "rows": len(rows),
            "accepted": counts["accepted"],
            "needs_verification": counts["needs_verification"],
            "rejected": counts["rejected"],
            "ambiguous": counts["ambiguous"],
            "duplicate": counts["duplicate"],
            "reasons": dict(reasons),
        }, ensure_ascii=False, indent=2))
