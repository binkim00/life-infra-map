from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence


class TagEvidenceAggregationTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="근거 집계 카페", category="cafe", address="서울", lat=37.5, lng=127,
            source="kakao_local", external_id="aggregation-1",
        )
        self.tag = Tag.objects.create(name="조용함")
        self.now = timezone.now()

    def add_evidence(self, *, source, reference, polarity="positive", expires=True):
        return PlaceTagEvidence.objects.create(
            place=self.place,
            tag=self.tag,
            source=source,
            source_reference=reference,
            polarity=polarity,
            confidence=70,
            evidence=f"{source} {polarity}",
            observed_at=self.now,
            expires_at=(self.now + timedelta(days=30)) if expires else (self.now - timedelta(days=1)),
        )

    def test_three_web_sources_raise_confidence_but_never_auto_confirm(self):
        for index in range(3):
            self.add_evidence(source="ai_suggested", reference=f"https://blog/{index}")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        tag = PlaceTag.objects.get(source="web_evidence")
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(tag.status, "candidate")
        self.assertFalse(tag.is_verified)
        self.assertEqual(tag.confidence, 75)

    def test_three_web_sources_plus_explicit_user_confirmation_can_confirm(self):
        for index in range(3):
            self.add_evidence(source="ai_suggested", reference=f"https://blog/{index}")
        self.add_evidence(source="user_feedback", reference="interaction:1")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        verified = PlaceTag.objects.get(source="user_verified")
        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(verified.is_verified)

    def test_admin_review_combined_with_web_evidence_can_confirm(self):
        self.add_evidence(source="ai_suggested", reference="https://blog/1")
        self.add_evidence(source="admin_review", reference="admin-review:1")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertEqual(result["confirmed_source"], "checked")
        self.assertTrue(PlaceTag.objects.get(source="checked").is_verified)

    def test_official_positive_evidence_can_confirm_without_web(self):
        self.add_evidence(source="field_rule", reference="official:field:1")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(PlaceTag.objects.get(source="field_rule").is_verified)

    def test_expired_and_negative_evidence_reduce_or_block_promotion(self):
        self.add_evidence(source="ai_suggested", reference="https://blog/expired", expires=False)
        self.add_evidence(source="ai_suggested", reference="https://blog/positive")
        self.add_evidence(source="ai_suggested", reference="https://blog/negative", polarity="negative")
        self.add_evidence(source="user_feedback", reference="interaction:1")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertEqual(result["status"], "needs_verification")
        self.assertEqual(result["evidence_state"], "CONFLICT")
        self.assertFalse(PlaceTag.objects.filter(source="user_verified", is_verified=True).exists())

    def test_single_positive_is_not_automatically_a_candidate(self):
        self.add_evidence(source="naver_blog_search", reference="https://blog/only")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertEqual(result["status"], "needs_verification")
        self.assertEqual(result["evidence_state"], "POSITIVE_DOMINANT")

    def test_negative_dominant_web_evidence_is_rejected(self):
        self.add_evidence(source="naver_blog_search", reference="https://blog/positive")
        for index in range(3):
            self.add_evidence(
                source="naver_blog_search",
                reference=f"https://blog/negative-{index}",
                polarity="negative",
            )
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["evidence_state"], "NEGATIVE_DOMINANT")
        aggregate = PlaceTag.objects.get(place=self.place, tag=self.tag, source="web_evidence")
        self.assertEqual(aggregate.status, "rejected")

    def test_official_negative_blocks_an_official_positive(self):
        self.add_evidence(source="field_rule", reference="official:positive")
        self.add_evidence(
            source="field_rule",
            reference="official:negative",
            polarity="negative",
        )

        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)

        self.assertEqual(result["status"], "rejected")
        rejected = PlaceTag.objects.get(source="field_rule")
        self.assertEqual(rejected.status, "rejected")
        self.assertFalse(rejected.is_verified)

    def test_official_negative_overrides_web_positive_candidate(self):
        for index in range(3):
            self.add_evidence(source="naver_blog_search", reference=f"https://blog/{index}")
        self.add_evidence(source="field_rule", reference="official:negative", polarity="negative")
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["evidence_state"], "NEGATIVE_DOMINANT")
        aggregate = PlaceTag.objects.get(place=self.place, tag=self.tag, source="web_evidence")
        self.assertEqual(aggregate.status, "rejected")
        self.assertIn("official negative evidence", aggregate.evidence)

    def test_expiry_revokes_only_confirmation_created_by_evidence_aggregation(self):
        web = [
            self.add_evidence(source="ai_suggested", reference=f"https://blog/{index}")
            for index in range(3)
        ]
        self.add_evidence(source="user_feedback", reference="interaction:1")
        aggregate_tag_evidence(self.place, self.tag, now=self.now)
        self.assertTrue(PlaceTag.objects.filter(
            source="user_verified", is_verified=True
        ).exists())

        for evidence in web:
            evidence.expires_at = self.now - timedelta(seconds=1)
            evidence.save(update_fields=["expires_at"])
        result = aggregate_tag_evidence(self.place, self.tag, now=self.now)

        self.assertEqual(result["status"], "none")
        self.assertFalse(PlaceTag.objects.filter(
            source="user_verified", is_verified=True
        ).exists())
