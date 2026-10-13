import io
import json

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence


class TagPromotionQueueTests(TestCase):
    def test_queue_reports_only_counts_and_internal_ids(self):
        place = Place.objects.create(
            name="비공개 시험 카페", category="cafe", lat=35.1, lng=129.1, source="test",
        )
        tag = Tag.objects.create(name="조용함")
        for index, source in enumerate(("naver_blog_search", "ai_suggested", "naver_blog_search")):
            PlaceTagEvidence.objects.create(
                place=place, tag=tag, source=source, polarity="positive",
                source_reference=f"https://publisher{index}.example/article",
                evidence=f"독립적인 조용함 관찰 {index}", confidence=85,
                observed_at=timezone.now(),
            )
        aggregate_tag_evidence(place, tag)
        output = io.StringIO()
        call_command("report_tag_promotion_queue", stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["review_queue"], 1)
        self.assertEqual(report["reasons"]["identity_and_independence_review"], 1)
        self.assertNotIn(place.name, output.getvalue())
