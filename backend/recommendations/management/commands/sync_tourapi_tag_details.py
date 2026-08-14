import os
from urllib.parse import unquote

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.management.commands.generate_meaningful_place_tags import generate_meaningful_tags
from recommendations.models import Place

TOUR_API_URL = 'https://apis.data.go.kr/B551011/KorService2/detailIntro2'


class Command(BaseCommand):
    help = 'Enrich TourAPI places with details for meaningful tags.'

    def add_arguments(self, parser):
        parser.add_argument('--after-id', type=int, default=0)
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--timeout', type=int, default=30)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        key = normalize_service_key(os.getenv('DATA_GO_KR_TOUR_SERVICE_KEY', '') or os.getenv('DATA_GO_KR_SERVICE_KEY', ''))
        if not key:
            raise CommandError('DATA_GO_KR_TOUR_SERVICE_KEY (or DATA_GO_KR_SERVICE_KEY) is required.')
        places = list(Place.objects.filter(source='tour_api', id__gt=options['after_id']).order_by('id')[:max(1, options['limit'])])
        stats = sync_tourapi_details(places, service_key=key, timeout=max(1, options['timeout']), dry_run=options['dry_run'])
        prefix = '[dry-run] ' if options['dry_run'] else ''
        message = '{}TourAPI sync: requested={} updated={} skipped={} failed={} last_id={} tags={}'.format(
            prefix, stats['requested'], stats['updated'], stats['skipped'], stats['failed'], stats['last_place_id'], stats['tag_matches'],
        )
        self.stdout.write(self.style.SUCCESS(message))


def sync_tourapi_details(places, *, service_key, timeout=30, dry_run=False, session=None):
    client = session or requests.Session()
    stats = {'requested': 0, 'updated': 0, 'skipped': 0, 'failed': 0, 'last_place_id': None, 'tag_matches': 0}
    updated_places = []
    for place in places:
        stats['last_place_id'] = place.id
        source = source_payload(place.raw)
        content_id = str(source.get('contentid') or '').strip()
        content_type_id = str(source.get('contenttypeid') or '').strip()
        if not content_id or not content_type_id:
            stats['skipped'] += 1
            continue
        stats['requested'] += 1
        try:
            response = client.get(TOUR_API_URL, params={
                'serviceKey': service_key,
                'MobileOS': 'ETC',
                'MobileApp': 'LifeInfraMap',
                '_type': 'json',
                'contentId': content_id,
                'contentTypeId': content_type_id,
                'numOfRows': 10,
                'pageNo': 1,
            }, timeout=timeout)
            response.raise_for_status()
            item = parse_tourapi_item(response.json())
        except (requests.RequestException, ValueError, TypeError, KeyError):
            stats['failed'] += 1
            continue
        if not item:
            stats['skipped'] += 1
            continue
        raw = dict(place.raw or {})
        sources = dict(raw.get('tag_evidence_sources') or {})
        sources['tourapi_intro'] = item
        raw['tag_evidence_sources'] = sources
        place.raw = raw
        updated_places.append(place)
        stats['updated'] += 1

    if not dry_run and updated_places:
        with transaction.atomic():
            Place.objects.bulk_update(updated_places, ['raw'], batch_size=500)
            result = generate_meaningful_tags(
                Place.objects.filter(id__in=[place.id for place in updated_places]),
                batch_size=500,
            )
            stats['tag_matches'] = result['matches']
    elif dry_run:
        from recommendations.services.meaningful_tag_rules import extract_meaningful_tags
        stats['tag_matches'] = sum(len(extract_meaningful_tags(place.raw)) for place in updated_places)
    return stats


def source_payload(raw):
    value = raw or {}
    while isinstance(value, dict) and isinstance(value.get('raw'), dict):
        value = value['raw']
    return value if isinstance(value, dict) else {}


def parse_tourapi_item(payload):
    response = payload.get('response') or {}
    header = response.get('header') or {}
    code = str(header.get('resultCode') or '')
    if code not in {'', '00', '0000'}:
        raise ValueError(header.get('resultMsg') or 'TourAPI error {}'.format(code))
    items = ((response.get('body') or {}).get('items') or {}).get('item') or []
    return items if isinstance(items, dict) else (items[0] if items else None)


def normalize_service_key(value):
    return unquote(str(value or '').strip())
