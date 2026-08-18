from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.semantic_sampling import stratified_feature_sample


class DynamicSemanticSamplingTests(TestCase):
    def test_default_sampling_discovers_eligible_categories_outside_pilot_list(self):
        place = Place.objects.create(
            name="Dynamic beach",
            category="beach",
            address="서울특별시 중구",
            lat=37.51,
            lng=127.01,
            source="test",
            external_id="semantic-dynamic-category",
        )
        tag = Tag.objects.create(name="산책좋음")
        PlaceTag.objects.create(
            place=place,
            tag=tag,
            source="web_evidence",
            status="confirmed",
            confidence=90,
        )
        PlaceTagEvidence.objects.create(
            place=place,
            tag=tag,
            source="tour_api",
            polarity="positive",
            confidence=90,
            evidence_key="dynamic-category",
            expires_at=timezone.now() + timedelta(days=1),
        )

        rows = stratified_feature_sample(limit=10, regions=("서울",))

        self.assertEqual([row["category"] for row in rows], ["beach"])
