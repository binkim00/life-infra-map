import hashlib
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import (
    PlaceInteractionEvent,
    PlaceTag,
    PlaceTagEvidence,
    Tag,
)


class Command(BaseCommand):
    help = 'Aggregate explicit feedback and behavioral signals into place tags.'

    def add_arguments(self, parser):
        parser.add_argument('--min-confirmations', type=int, default=3)
        parser.add_argument('--min-behavior-actors', type=int, default=5)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        stats = aggregate_place_tag_interactions(
            min_confirmations=max(1, options['min_confirmations']),
            min_behavior_actors=max(2, options['min_behavior_actors']),
            dry_run=options['dry_run'],
        )
        self.stdout.write(
            self.style.SUCCESS(
                'Tag interaction aggregation complete: '
                'explicit_groups={} evidence={} behavioral_groups={}'.format(
                    stats['explicit_groups'],
                    stats['evidence'],
                    stats['behavioral_groups'],
                )
            )
        )


def aggregate_place_tag_interactions(
    *,
    min_confirmations=3,
    min_behavior_actors=5,
    dry_run=False,
    place_ids=None,
    tag_names=None,
):
    stats = {
        'explicit_groups': 0,
        'evidence': 0,
        'behavioral_groups': 0,
    }
    explicit_events = PlaceInteractionEvent.objects.filter(
        event_type__in=['tag_confirm', 'tag_reject'],
        place__isnull=False,
    ).exclude(tag_name='').select_related('place', 'user').order_by('created_at', 'id')
    if place_ids:
        explicit_events = explicit_events.filter(place_id__in=place_ids)
    if tag_names:
        explicit_events = explicit_events.filter(tag_name__in=tag_names)
    explicit_groups = defaultdict(dict)
    for event in explicit_events.iterator():
        actor = actor_key(event)
        explicit_groups[(event.place_id, event.tag_name)][actor] = event

    for (place_id, tag_name), actor_events in explicit_groups.items():
        votes = list(actor_events.values())
        positives = sum(event.event_type == 'tag_confirm' for event in votes)
        negatives = sum(event.event_type == 'tag_reject' for event in votes)
        score = positives - negatives
        confirmed = positives >= min_confirmations and score >= 2
        rejected = negatives >= min_confirmations and score <= -2
        status = 'confirmed' if confirmed else 'rejected' if rejected else 'candidate'
        confidence = max(10, min(95, 50 + score * 10))
        stats['explicit_groups'] += 1
        stats['evidence'] += len(votes)
        if dry_run:
            continue

        tag, _ = Tag.objects.get_or_create(
            name=tag_name,
            defaults={
                'tag_type': 'recommendation',
                'description': 'Collected from explicit user place feedback',
            },
        )
        PlaceTag.objects.update_or_create(
            place_id=place_id,
            tag=tag,
            source='user_verified',
            defaults={
                'status': status,
                'confidence': confidence,
                'evidence': '{} confirmations, {} rejections'.format(
                    positives,
                    negatives,
                ),
                'is_verified': confirmed,
                'verified_at': timezone.now() if confirmed else None,
            },
        )
        for event in votes:
            polarity = 'positive' if event.event_type == 'tag_confirm' else 'negative'
            reference = 'interaction:{}'.format(event.id)
            evidence_key = hashlib.sha256(reference.encode('utf-8')).hexdigest()
            PlaceTagEvidence.objects.update_or_create(
                evidence_key=evidence_key,
                defaults={
                    'place_id': place_id,
                    'tag': tag,
                    'user': event.user,
                    'source': 'user_feedback',
                    'source_reference': reference,
                    'polarity': polarity,
                    'confidence': 90,
                    'evidence': 'User {} tag {}'.format(
                        'confirmed' if polarity == 'positive' else 'rejected',
                        tag_name,
                    ),
                    'context': {
                        **event.context,
                        'search_id': event.search_id,
                        'event_type': event.event_type,
                    },
                    'observed_at': event.created_at,
                    'raw': {'interaction_event_id': event.id},
                },
            )

    behavior_groups = defaultdict(lambda: defaultdict(float))
    behavior_events = PlaceInteractionEvent.objects.filter(
        event_type__in=['click', 'save', 'dismiss'],
        place__isnull=False,
    ).exclude(requested_tags=[]).order_by('created_at', 'id')
    if place_ids:
        behavior_events = behavior_events.filter(place_id__in=place_ids)
    weights = {'click': 1.0, 'save': 3.0, 'dismiss': -2.0}
    for event in behavior_events.iterator():
        actor = actor_key(event)
        for tag_name in event.requested_tags[:20]:
            normalized = str(tag_name or '').strip().lstrip('#')[:50]
            if normalized:
                behavior_groups[(event.place_id, normalized)][actor] += weights[event.event_type]

    for (place_id, tag_name), actor_scores in behavior_groups.items():
        if len(actor_scores) < min_behavior_actors:
            continue
        score = sum(max(-2, min(3, value)) for value in actor_scores.values())
        if score < min_behavior_actors:
            continue
        stats['behavioral_groups'] += 1
        if dry_run:
            continue
        tag, _ = Tag.objects.get_or_create(
            name=tag_name,
            defaults={
                'tag_type': 'recommendation',
                'description': 'Candidate inferred from aggregate search behavior',
            },
        )
        confidence = max(50, min(70, int(50 + score)))
        PlaceTag.objects.update_or_create(
            place_id=place_id,
            tag=tag,
            source='interaction_signal',
            defaults={
                'status': 'candidate',
                'confidence': confidence,
                'evidence': '{} actors, weighted score {:.1f}'.format(
                    len(actor_scores),
                    score,
                ),
                'is_verified': False,
                'verified_at': None,
            },
        )
    return stats


def actor_key(event):
    if event.user_id:
        return 'user:{}'.format(event.user_id)
    if event.session_key:
        return 'session:{}'.format(event.session_key)
    return 'event:{}'.format(event.id)
