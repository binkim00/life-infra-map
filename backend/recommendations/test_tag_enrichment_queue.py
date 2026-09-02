from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.models import (
    Place, PlaceInteractionEvent, PlaceTag, PlaceTagEvidence, Tag, TagEnrichmentRequest,
)
from recommendations.services.tag_enrichment_queue import enqueue_tag_enrichment, normalize_subjective_tags


class TagEnrichmentQueueTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name='광안리 테스트 식당', category='restaurant',
            address='부산광역시 수영구', lat=35.15, lng=129.11,
            source='kakao_local', external_id='kakao-queue-1',
        )

    def test_understands_subjective_aliases_in_natural_language(self):
        self.assertEqual(
            set(normalize_subjective_tags([], query='광안리 한적하고 혼밥하기 좋은 식당')),
            {'조용함', '혼밥좋음'},
        )

    def test_search_impression_creates_and_prioritizes_requests(self):
        search = PlaceInteractionEvent.objects.create(
            event_type='search', search_id='search-1',
            query='광안리 조용한 분위기 좋은 식당',
            requested_tags=['조용한', '분위기 좋은'],
        )
        impression = PlaceInteractionEvent.objects.create(
            event_type='impression', search_id='search-1', place=self.place,
            query=search.query, requested_tags=search.requested_tags,
        )

        enqueue_tag_enrichment([search, impression])
        enqueue_tag_enrichment([search, impression])

        self.assertEqual(TagEnrichmentRequest.objects.count(), 2)
        request = TagEnrichmentRequest.objects.get(tag_name='조용함')
        self.assertEqual(request.demand_count, 2)
        self.assertEqual(request.priority, 2)

    def test_does_not_queue_already_verified_tag(self):
        tag = Tag.objects.create(name='조용함', tag_type='recommendation')
        PlaceTag.objects.create(
            place=self.place, tag=tag, source='user_verified',
            status='confirmed', confidence=95, is_verified=True,
        )
        impression = PlaceInteractionEvent.objects.create(
            event_type='impression', search_id='search-2', place=self.place,
            query='조용한 식당', requested_tags=['조용함'],
        )

        enqueue_tag_enrichment([impression])

        self.assertFalse(TagEnrichmentRequest.objects.exists())

    def test_does_not_reopen_request_while_fresh_evidence_exists(self):
        tag = Tag.objects.create(name='조용함', tag_type='recommendation')
        PlaceTagEvidence.objects.create(
            place=self.place,
            tag=tag,
            source='web_search',
            source_reference='https://example.com/fresh-evidence',
            polarity='positive',
            evidence='조용하게 이용하기 좋다는 최근 근거',
            expires_at=timezone.now() + timedelta(days=30),
        )
        request = TagEnrichmentRequest.objects.create(
            place=self.place,
            tag_name='조용함',
            status='completed',
        )
        impression = PlaceInteractionEvent.objects.create(
            event_type='impression', search_id='search-3', place=self.place,
            query='조용한 식당', requested_tags=['조용함'],
        )

        enqueue_tag_enrichment([impression])

        request.refresh_from_db()
        self.assertEqual(request.status, 'completed')
        self.assertEqual(request.demand_count, 1)
