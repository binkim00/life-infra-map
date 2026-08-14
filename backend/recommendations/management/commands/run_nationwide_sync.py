import os
from urllib.parse import unquote

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from recommendations.management.commands.sync_localdata_api import sync_localdata_api
from recommendations.models import DataSourceSyncRun
from recommendations.services.data_source_manifest import get_dataset_config


DEFAULT_DATASETS = (
    'general_restaurant',
    'rest_restaurant',
    'bakery',
)


class Command(BaseCommand):
    help = 'Resume LOCALDATA API syncs, then rebuild searchable nationwide data.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', action='append', dest='datasets')
        parser.add_argument('--page-size', type=int, default=100)
        parser.add_argument('--max-pages', type=int, default=100)
        parser.add_argument('--timeout', type=int, default=30)
        parser.add_argument('--no-resume', action='store_true')
        parser.add_argument('--skip-enrichment', action='store_true')
        parser.add_argument('--continue-on-error', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        datasets = options['datasets'] or DEFAULT_DATASETS
        results = []
        failures = []

        for dataset in datasets:
            try:
                manifest, config = get_dataset_config('localdata', dataset)
                key_name = config.get(
                    'service_key_environment_variable',
                    manifest['service_key_environment_variable'],
                )
                service_key = unquote(os.getenv(key_name, '').strip())
                if not service_key:
                    raise CommandError(
                        '{} is not configured for {}.'.format(key_name, dataset)
                    )

                start_page = 1
                if not options['no_resume'] and not options['dry_run']:
                    start_page = resumable_page(dataset)
                stats = sync_localdata_api(
                    dataset=dataset,
                    dataset_config=config,
                    service_key=service_key,
                    page_size=max(1, min(options['page_size'], 1000)),
                    start_page=start_page,
                    max_pages=max(1, options['max_pages']),
                    timeout=max(1, options['timeout']),
                    dry_run=options['dry_run'],
                )
                results.append((dataset, start_page, stats))
                self.stdout.write(
                    self.style.SUCCESS(
                        '{}: start_page={} pages={} read={} exhausted={}'.format(
                            dataset,
                            start_page,
                            stats['pages'],
                            stats['read'],
                            stats['exhausted'],
                        )
                    )
                )
            except Exception as exc:
                failures.append((dataset, str(exc)))
                self.stderr.write(self.style.ERROR('{}: {}'.format(dataset, exc)))
                if not options['continue_on_error']:
                    raise CommandError(str(exc)) from exc

        if results and not options['skip_enrichment']:
            enrichment_options = {'source': 'localdata'}
            if options['dry_run']:
                enrichment_options['dry_run'] = True
            call_command('promote_source_places', **enrichment_options)
            call_command('generate_objective_place_tags', **enrichment_options)
            if not options['dry_run']:
                call_command(
                    'rebuild_place_coverage',
                    source='localdata',
                    prune=True,
                )

        if failures:
            summary = ', '.join(
                '{}: {}'.format(dataset, message)
                for dataset, message in failures
            )
            raise CommandError(
                'Nationwide sync completed with failures: {}'.format(summary)
            )


def resumable_page(dataset):
    latest = (
        DataSourceSyncRun.objects.filter(source='localdata', dataset=dataset)
        .order_by('-started_at')
        .first()
    )
    if latest is None or latest.stats.get('exhausted') is True:
        return 1
    try:
        return max(1, int(latest.cursor.get('next_page', 1)))
    except (TypeError, ValueError):
        return 1
