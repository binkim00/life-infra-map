from django.core.management.base import BaseCommand

from recommendations.services.operations_dashboard import refresh_operations_snapshot


class Command(BaseCommand):
    help = "Refresh heavyweight Region x Category x Tag admin dashboard coverage aggregates."

    def handle(self, *args, **options):
        snapshot = refresh_operations_snapshot()
        self.stdout.write(
            self.style.SUCCESS(
                f"snapshot_date={snapshot.snapshot_date} generated_at={snapshot.generated_at.isoformat()}"
            )
        )
