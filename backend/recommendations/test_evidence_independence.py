from django.test import TestCase

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.tag_evidence_aggregation import independent_count


class EvidenceIndependenceTests(TestCase):
    def test_same_publisher_or_mirrored_quote_is_not_independent(self):
        place = Place.objects.create(name="검사 카페", category="cafe", lat=35.1, lng=129.1, source="test")
        tag = Tag.objects.create(name="조용함")
        for reference, quote in (
            ("https://blog.naver.com/author_a/1", "조용하고 편안한 카페"),
            ("https://m.blog.naver.com/author_a/2", "자리도 넓고 조용해요"),
            ("https://blog.naver.com/author_b/3", "조용하고 편안한 카페"),
            ("https://blog.naver.com/author_c/4", "혼자 있기 조용한 공간"),
        ):
            PlaceTagEvidence.objects.create(
                place=place, tag=tag, source="naver_blog_search",
                source_reference=reference, evidence=quote, confidence=80,
            )
        self.assertEqual(independent_count(PlaceTagEvidence.objects.filter(place=place, tag=tag)), 2)
