import hashlib
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence, Tag, TagEnrichmentRequest
from recommendations.services.subjective_tag_evidence_provider import collect_subjective_tag_evidence


class Command(BaseCommand):
    help = 'Process demand-prioritized subjective tag evidence requests.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        stats = process_queue(limit=max(1, options['limit']), dry_run=options['dry_run'])
        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            '{}Tag enrichment: processed={} candidates={} negative={} insufficient={} failed={}'.format(
                prefix, stats['processed'], stats['candidates'], stats['negative'], stats['insufficient'], stats['failed'],
            )
        ))


def process_queue(*, limit=10, dry_run=False, evidence_provider=None):
    provider = evidence_provider or collect_subjective_tag_evidence
    now = timezone.now()
    requests = list(TagEnrichmentRequest.objects.filter(
        status='queued',
    ).filter(next_attempt_at__isnull=True).select_related('place').order_by('-priority', 'created_at')[:limit])
    stats = {'processed': 0, 'candidates': 0, 'negative': 0, 'insufficient': 0, 'failed': 0}
    for request in requests:
        stats['processed'] += 1
        if dry_run:
            continue
        request.status = 'processing'
        request.locked_at = now
        request.save(update_fields=['status', 'locked_at', 'updated_at'])
        try:
            result = provider(request.place, request.tag_name)
        except Exception as exc:
            result = {'executed': True, 'error': exc.__class__.__name__}
        if not result.get('executed') or result.get('error') == 'request_failed':
            request.status = 'failed'
            request.error_message = str(result.get('error') or 'provider_failed')[:1000]
            request.next_attempt_at = now + timedelta(hours=6)
            stats['failed'] += 1
        elif not result.get('evidences') and result.get('polarity') not in {'positive', 'negative'}:
            request.status = 'completed'
            request.error_message = str(result.get('error') or 'insufficient_evidence')[:1000]
            stats['insufficient'] += 1
        else:
            evidences = result.get('evidences') or [result]
            for evidence in evidences:
                evidence_time = now
                if evidence.get('observed_date'):
                    try:
                        evidence_time = timezone.make_aware(datetime.fromisoformat(evidence['observed_date']))
                    except (TypeError, ValueError):
                        evidence_time = now
                save_candidate_evidence(request, evidence, observed_at=evidence_time)
            request.status = 'completed'
            request.error_message = ''
            positive_count = sum(1 for evidence in evidences if evidence.get('polarity') == 'positive')
            negative_count = sum(1 for evidence in evidences if evidence.get('polarity') == 'negative')
            stats['candidates'] += positive_count
            stats['negative'] += negative_count
        request.locked_at = None
        request.save(update_fields=['status', 'error_message', 'next_attempt_at', 'locked_at', 'updated_at'])
    return stats


def save_candidate_evidence(request, result, *, observed_at):
    save_place_candidate_evidence(
        request.place,
        request.tag_name,
        result,
        observed_at=observed_at,
    )


def save_place_candidate_evidence(place, tag_name, result, *, observed_at):
    tag, _ = Tag.objects.get_or_create(
        name=tag_name,
        defaults={'tag_type': 'recommendation', 'description': '수요 기반 웹 근거 후보 태그'},
    )
    source_url = result['source_url']
    polarity = result['polarity']
    key_value = '{}|{}|ai_suggested|{}|{}'.format(place.id, tag.id, source_url, polarity)
    PlaceTagEvidence.objects.update_or_create(
        evidence_key=hashlib.sha256(key_value.encode('utf-8')).hexdigest(),
        defaults={
            'place': place,
            'tag': tag,
            'source': 'ai_suggested',
            'source_reference': source_url,
            'polarity': polarity,
            'confidence': 55,
            'evidence': result['evidence_summary'],
            'context': {'source_title': result.get('source_title', ''), 'subjective': True},
            'raw': result.get('raw') or {},
            'observed_at': observed_at,
            'expires_at': observed_at + timedelta(days=120),
        },
    )
    refresh_candidate_aggregate(place, tag)


def refresh_candidate_aggregate(place, tag):
    from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence

    aggregate_tag_evidence(place, tag)
