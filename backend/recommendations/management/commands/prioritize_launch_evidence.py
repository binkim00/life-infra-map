import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommendations.services.launch_evidence_priority import prioritize_launch_evidence


class Command(BaseCommand):
    help = "Convert launch evaluation gaps into prioritized place/tag evidence requests."

    def add_arguments(self, parser):
        parser.add_argument("evaluation")
        parser.add_argument("--output", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["evaluation"])
        if not path.exists():
            raise CommandError("Evaluation file does not exist: {}".format(path))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("Invalid evaluation JSON: {}".format(exc)) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise CommandError("Evaluation must contain a results list.")
        report = prioritize_launch_evidence(payload, dry_run=options["dry_run"])
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(rendered)
        if options["output"]:
            output = Path(options["output"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
