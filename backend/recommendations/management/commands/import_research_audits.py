import json
from pathlib import Path
from django.core.management.base import BaseCommand
from recommendations.models import ResearchAudit


class Command(BaseCommand):
    help = "Import retained validation summaries without rerunning or inventing judgments."

    def add_arguments(self, parser):
        parser.add_argument("directory")

    def handle(self, *args, **options):
        count = 0
        for path in sorted(Path(options["directory"]).glob("validation-*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("dry_run", True):
                continue
            ResearchAudit.objects.get_or_create(run_key=path.name, defaults={"payload": payload})
            count += 1
        self.stdout.write(f"Imported/preserved {count} collection summaries")
