import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from recommendations.management.commands.run_nationwide_sync import DEFAULT_DATASETS
from recommendations.models import DataSourceSyncRun, PlaceCoverage


class Command(BaseCommand):
    help = 'Check LOCALDATA sync freshness, failures, and nationwide coverage.'

    def add_arguments(self, parser):
        parser.add_argument('--max-age-hours', type=int, default=48)
        parser.add_argument('--min-coverage-score', type=float, default=20)

    def handle(self, *args, **options):
        report = build_health_report(
            max_age_hours=max(1, options['max_age_hours']),
            min_coverage_score=max(
                0,
                min(options['min_coverage_score'], 100),
            ),
        )
        self.stdout.write(
            json.dumps(report, ensure_ascii=False, indent=2, default=str)
        )
        if not report['healthy']:
            raise CommandError('Nationwide data health check failed.')


def build_health_report(*, max_age_hours=48, min_coverage_score=20):
    stale_before = timezone.now() - timedelta(hours=max_age_hours)
    dataset_reports = []
    problems = []

    for dataset in DEFAULT_DATASETS:
        latest = (
            DataSourceSyncRun.objects.filter(source='localdata', dataset=dataset)
            .order_by('-started_at')
            .first()
        )
        if latest is None:
            dataset_reports.append({'dataset': dataset, 'status': 'missing'})
            problems.append('{}: no sync run'.format(dataset))
            continue
        state = 'ok'
        if latest.status == 'failed':
            state = 'failed'
            problems.append('{}: latest sync failed'.format(dataset))
        elif latest.started_at < stale_before:
            state = 'stale'
            problems.append('{}: latest sync is stale'.format(dataset))
        dataset_reports.append(
            {
                'dataset': dataset,
                'status': state,
                'run_status': latest.status,
                'started_at': latest.started_at,
                'completed_at': latest.completed_at,
                'next_page': latest.cursor.get('next_page'),
                'exhausted': latest.stats.get('exhausted', False),
                'error': latest.error_message,
            }
        )

    coverage = PlaceCoverage.objects.filter(source='localdata')
    coverage_cells = coverage.count()
    low_coverage_cells = coverage.filter(
        coverage_score__lt=min_coverage_score
    ).count()
    if coverage_cells == 0:
        problems.append('coverage: no cells')

    return {
        'healthy': not problems,
        'checked_at': timezone.now(),
        'datasets': dataset_reports,
        'coverage': {
            'cells': coverage_cells,
            'low_score_cells': low_coverage_cells,
            'minimum_score': min_coverage_score,
        },
        'problems': problems,
    }
