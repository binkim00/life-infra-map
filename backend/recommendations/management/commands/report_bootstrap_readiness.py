import json
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.services.coverage_reporting import build_coverage_report


class Command(BaseCommand):
    help = "Report Tag x Category x Region coverage and bootstrap readiness."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/bootstrap_readiness.json")

    def handle(self, *args, **options):
        report = build_coverage_report()
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            "Bootstrap readiness: output={} regions={} cells={}".format(
                path, len(report["regions"]), len(report["cells"])
            )
        ))

