import json

from django.core.management.base import BaseCommand, CommandError

from recommendations.services.region_enrichment import build_region_enrichment_report


class Command(BaseCommand):
    help = "Report focused cafe/restaurant enrichment coverage and recent collection ROI."

    def add_arguments(self, parser):
        parser.add_argument("region")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        try:
            report = build_region_enrichment_report(options["region"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        self.stdout.write(f"Focus Region: {report['region']} ({report['state']})")
        for category, row in report["categories"].items():
            self.stdout.write(
                f"{category}: places={row['places']} evidence_places={row['evidence_places']} "
                f"active_places={row['active_evidence_places']} place_tags={row['place_tags']}"
            )
            for tag in row["tags"]:
                self.stdout.write(
                    f"  {tag['tag']}: active={tag['active_places']} coverage={tag['coverage']:.4f}"
                )
            self.stdout.write("  priority_pool=" + json.dumps(row["priority_pool"], ensure_ascii=False))
        for index, cycle in enumerate(report["recent_cycles"], 1):
            self.stdout.write(
                f"cycle{index}: calls={cycle['calls']} places={cycle['places']} "
                f"evidence/API={cycle['evidence_per_call']:.4f} active/API={cycle['active_per_call']:.4f}"
            )
        self.stdout.write(f"Recommendation: {report['state']}")
