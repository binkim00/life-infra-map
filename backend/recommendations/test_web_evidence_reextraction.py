from datetime import timedelta
from io import StringIO
import json

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence, Tag


class WebEvidenceReextractionTests(TestCase):
    def test_reextracts_multiple_tags_and_inherits_freshness_idempotently(self):
        place = Place.objects.create(
            name="근거 카페", category="cafe", address="서울특별시 중구",
            lat=37.5, lng=127.0, source="test", external_id="reextract-1",
        )
        ambience = Tag.objects.create(name="분위기좋음")
        Tag.objects.create(name="콘센트있음")
        Tag.objects.create(name="혼자이용좋음")
        expires = timezone.now() - timedelta(days=2)
        original = PlaceTagEvidence.objects.create(
            place=place, tag=ambience, source="naver_blog_search",
            source_reference="https://example.com/post", polarity="positive",
            confidence=70,
            evidence="혼자 책 읽기 좋고 자리마다 콘센트가 있었다",
            context={"source_title": "근거 카페 방문기"},
            observed_at=timezone.now() - timedelta(days=200), expires_at=expires,
        )

        dry = StringIO()
        call_command("reextract_web_evidence_tags", stdout=dry)
        self.assertEqual(json.loads(dry.getvalue())["additional_place_tag_pairs"], 2)
        self.assertEqual(PlaceTagEvidence.objects.count(), 1)

        call_command("reextract_web_evidence_tags", apply=True, stdout=StringIO())
        derived = PlaceTagEvidence.objects.exclude(pk=original.pk)
        self.assertEqual(set(derived.values_list("tag__name", flat=True)), {"콘센트있음", "혼자이용좋음"})
        self.assertTrue(all(row.expires_at == expires for row in derived))

        second = StringIO()
        call_command("reextract_web_evidence_tags", apply=True, stdout=second)
        self.assertEqual(json.loads(second.getvalue())["created_evidence"], 0)
        self.assertEqual(PlaceTagEvidence.objects.count(), 3)
