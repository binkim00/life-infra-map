from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence, TagEnrichmentRequest
from recommendations.services.canonical_tag_policy import CANONICAL_TAG_ALIASES

SUBJECTIVE_TAG_ALIASES = CANONICAL_TAG_ALIASES


def normalize_subjective_tags(values, query=''):
    texts = [str(value or '').strip().lower() for value in values or []]
    texts.append(str(query or '').strip().lower())
    matches = []
    for tag, aliases in SUBJECTIVE_TAG_ALIASES.items():
        if any(alias in text for text in texts for alias in aliases):
            matches.append(tag)
    return matches


def enqueue_tag_enrichment(events):
    searches = {
        event.search_id: event
        for event in events
        if event.event_type == 'search' and event.search_id
    }
    queued = 0
    with transaction.atomic():
        for event in events:
            if event.event_type not in {'impression', 'click', 'save'} or not event.place_id:
                continue
            search = searches.get(event.search_id)
            query = event.query or (search.query if search else '')
            requested = event.requested_tags or (search.requested_tags if search else [])
            tags = normalize_subjective_tags(requested, query=query)
            confirmed = set(PlaceTag.objects.filter(
                place_id=event.place_id,
                tag__name__in=tags,
                status='confirmed',
                is_verified=True,
            ).values_list('tag__name', flat=True))
            evidenced = set(PlaceTagEvidence.objects.filter(
                place_id=event.place_id,
                tag__name__in=tags,
                polarity__in=('positive', 'negative'),
            ).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
            ).values_list('tag__name', flat=True))
            for tag_name in set(tags) - confirmed - evidenced:
                request, created = TagEnrichmentRequest.objects.get_or_create(
                    place_id=event.place_id,
                    tag_name=tag_name,
                    defaults={
                        'source_query': query,
                        'context': {'search_id': event.search_id, 'event_type': event.event_type},
                    },
                )
                if not created:
                    request.demand_count += 1
                    request.priority = min(100000, request.priority + 1)
                    request.status = 'queued'
                    request.next_attempt_at = None
                    request.source_query = query or request.source_query
                    request.error_message = ''
                    request.save(update_fields=[
                        'demand_count', 'priority', 'status', 'next_attempt_at', 'source_query',
                        'error_message', 'last_requested_at', 'updated_at',
                    ])
                queued += 1
    return queued
