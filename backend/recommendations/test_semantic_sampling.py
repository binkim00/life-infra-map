from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.semantic_sampling import stratified_feature_sample


class SemanticSamplingTests(TestCase):
    def test_only_active_positive_supported_features_are_sampled(self):
        place = Place.objects.create(
            name="표본 카페", category="cafe", address="서울특별시 중구",
            lat=37.5, lng=127.0, source="test", external_id="semantic-sample",
        )
        active = Tag.objects.create(name="조용함")
        stale = Tag.objects.create(name="분위기좋음")
        for tag in (active, stale):
            PlaceTag.objects.create(
                place=place, tag=tag, source="web_evidence", status="candidate", confidence=70,
            )
        PlaceTagEvidence.objects.create(
            place=place, tag=active, source="naver_blog_search", polarity="positive",
            confidence=70, evidence_key="active", expires_at=timezone.now() + timedelta(days=1),
        )
        PlaceTagEvidence.objects.create(
            place=place, tag=stale, source="naver_blog_search", polarity="positive",
            confidence=70, evidence_key="stale", expires_at=timezone.now() - timedelta(days=1),
        )
        rows = stratified_feature_sample(limit=10, regions=("서울",), categories=("cafe",))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["features"], ["조용함"])
