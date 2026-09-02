from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from recommendations.management.commands.process_tag_enrichment_queue import process_queue
from recommendations.models import Place, PlaceTag, PlaceTagEvidence, TagEnrichmentRequest


class TagEnrichmentWorkerTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name='서면 테스트 카페', category='cafe',
            address='부산광역시 부산진구', lat=35.15, lng=129.05,
            source='kakao_local', external_id='worker-place-1',
        )
        self.request = TagEnrichmentRequest.objects.create(
            place=self.place, tag_name='조용함', priority=3,
        )

    def test_saves_single_sourced_web_result_for_verification(self):
        def provider(place, tag_name):
            return {
                'executed': True,
                'polarity': 'positive',
                'evidence_summary': '평일에는 조용하게 머물기 좋다고 소개한다.',
                'source_url': 'https://example.com/place-review',
                'source_title': '장소 소개',
            }

        stats = process_queue(limit=1, evidence_provider=provider)

        self.request.refresh_from_db()
        candidate = PlaceTag.objects.get()
        evidence = PlaceTagEvidence.objects.get()
        self.assertEqual(stats['candidates'], 1)
        self.assertEqual(self.request.status, 'completed')
        self.assertEqual(candidate.status, 'needs_verification')
        self.assertEqual(candidate.source, 'web_evidence')
        self.assertFalse(candidate.is_verified)
        self.assertEqual(evidence.source_reference, 'https://example.com/place-review')
        self.assertIsNotNone(evidence.expires_at)

    def test_single_negative_evidence_requires_verification(self):
        def provider(place, tag_name):
            return {
                'executed': True,
                'polarity': 'negative',
                'evidence_summary': '혼잡하고 음악 소리가 크다고 명시한다.',
                'source_url': 'https://example.com/noisy',
            }

        stats = process_queue(limit=1, evidence_provider=provider)

        self.assertEqual(stats['negative'], 1)
        aggregate = PlaceTag.objects.get()
        self.assertEqual(aggregate.status, 'needs_verification')
        self.assertEqual(PlaceTagEvidence.objects.get().polarity, 'negative')

    def test_rejects_result_without_source(self):
        stats = process_queue(
            limit=1,
            evidence_provider=lambda place, tag: {
                'executed': True, 'polarity': 'unknown',
                'error': 'insufficient_evidence',
            },
        )

        self.assertEqual(stats['insufficient'], 1)
        self.assertFalse(PlaceTagEvidence.objects.exists())

    def test_aggregates_independent_positive_and_negative_urls(self):
        evidences = [
            {
                'polarity': 'positive',
                'evidence_summary': '조용하다는 근거 {}'.format(index),
                'source_url': 'https://example.com/positive-{}'.format(index),
            }
            for index in range(3)
        ]
        evidences.append({
            'polarity': 'negative',
            'evidence_summary': '주말에는 시끄럽다는 근거',
            'source_url': 'https://example.com/negative',
        })

        process_queue(
            limit=1,
            evidence_provider=lambda place, tag: {
                'executed': True,
                'evidences': evidences,
            },
        )

        self.assertEqual(PlaceTagEvidence.objects.count(), 4)
        self.assertEqual(PlaceTag.objects.get().confidence, 66)

    def test_reconciliation_closes_request_with_active_evidence(self):
        tag = self._create_active_evidence()
        output = StringIO()

        call_command("reconcile_tag_enrichment_requests", "--apply", stdout=output)

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "completed")
        self.assertIn("matched=1 updated=1", output.getvalue())
        self.assertEqual(PlaceTagEvidence.objects.get().tag, tag)

    def _create_active_evidence(self):
        from recommendations.models import Tag

        tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        PlaceTagEvidence.objects.create(
            place=self.place,
            tag=tag,
            source="web_search",
            source_reference="https://example.com/already-collected",
            polarity="positive",
            evidence="이미 수집된 유효 근거",
            expires_at=timezone.now() + timedelta(days=30),
        )
        return tag
