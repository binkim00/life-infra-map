import json

from django.core.management.base import BaseCommand, CommandError

from recommendations.services.operations_dashboard import build_operations_dashboard


class Command(BaseCommand):
    help = "Report admin collection growth and coverage metrics from the shared dashboard service."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=1, choices=(1, 7, 30))
        parser.add_argument("--region", default="")
        parser.add_argument("--category", default="")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        try:
            payload = build_operations_dashboard(
                days=options["days"],
                region=options["region"].strip(),
                category=options["category"].strip(),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if options["as_json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            return

        period = payload["period"]
        self.stdout.write(
            "days={days} processed_places={processed_places} new_evidence={new_evidence} "
            "new_active_evidence={new_active_evidence} new_place_tags={new_place_tags} "
            "evidence_places={evidence_places}".format(days=options["days"], **period)
        )
        for provider in payload["providers"]:
            self.stdout.write(
                "provider={provider} calls={calls} success={success} failures={failures} 429={rate_limited}".format(
                    **provider
                )
            )
        for row in payload["strategies"]:
            self.stdout.write(
                "strategy={strategy} places={places} calls={calls} evidence={evidence} "
                "active={active} evidence/api={evidence_per_call} active/api={active_per_call}".format(**row)
            )
        for row in payload["top_active_tags"]:
            self.stdout.write("tag={tag} new_active={count}".format(**row))
