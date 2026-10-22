from datetime import timedelta

from django.db import connection
from django.db.models import Prefetch
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from recommendations.models import EvidenceReview, Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.ai_search_orchestrator import _db_tag_lists
from recommendations.services.confirmation_evidence import confirmation_aware_place_tags
from recommendations.services.db_recommender import get_place_tag_data


class ConfirmationEvidenceTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.place = Place.objects.create(
            name="확인 근거 검사 카페", category="cafe", address="서울",
            lat=37.5, lng=127, source="test", external_id="confirmation",
        )
        self.tag = Tag.objects.create(name="조용함")
        self.confirmation = PlaceTag.objects.create(
            place=self.place, tag=self.tag, source="checked", status="confirmed",
            is_verified=True, confidence=90, evidence="기존 수동 확인 기록",
        )

    def evidence(self, *, review=None, **kwargs):
        defaults = dict(
            place=self.place, tag=self.tag, source="admin_review",
            polarity="positive", evidence="직접 확인한 관측 내용",
            observed_at=self.now, expires_at=self.now + timedelta(days=1),
        )
        defaults.update(kwargs)
        row = PlaceTagEvidence.objects.create(**defaults)
        if review is not None:
            EvidenceReview.objects.create(evidence=row, status=review)
        return row

    def assert_visible(self, expected):
        db = get_place_tag_data(self.place)
        ai = _db_tag_lists(self.place)
        self.assertEqual(self.tag.name in db["verified_tags"], expected)
        self.assertEqual(self.tag.name in ai["verified"], expected)
        if not expected:
            for key in ("suggested_tags", "warning_tags", "historical_tags"):
                self.assertNotIn(self.tag.name, db[key])
            self.assertNotIn(self.tag.name, [d["name"] for d in db["tag_details"]])
            for key in ("suggested", "candidate", "warning", "historical"):
                self.assertNotIn(self.tag.name, ai[key])

    def test_missing_evidence_is_not_current_or_suggested(self):
        self.assert_visible(False)

    def test_expired_confirmation_is_excluded_without_changing_records(self):
        old = self.evidence(expires_at=self.now - timedelta(days=1))
        review = EvidenceReview.objects.create(evidence=old, status="approved")
        before = (self.confirmation.__dict__.copy(), old.__dict__.copy(), review.__dict__.copy())
        with CaptureQueriesContext(connection) as queries:
            self.assert_visible(False)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        for row, values in zip((self.confirmation, old, review), before):
            row.refresh_from_db()
            for key, value in values.items():
                if not key.startswith("_"):
                    self.assertEqual(getattr(row, key), value)

    def test_user_verified_requires_evidence_too(self):
        self.confirmation.source = "user_verified"
        self.confirmation.save()
        self.assert_visible(False)
        self.evidence(source="user_feedback")
        self.assert_visible(True)

    def test_current_manual_evidence_preserves_confirmation(self):
        self.evidence()
        self.assert_visible(True)

    def test_no_expiry_manual_observation_preserves_existing_policy(self):
        self.evidence(expires_at=None)
        self.assert_visible(True)

    def test_current_approved_web_evidence_preserves_confirmation(self):
        self.evidence(source="naver_blog_search", review="approved")
        self.assert_visible(True)

    def test_unapproved_web_and_nonaccepted_reviews_do_not_support(self):
        for status in (None, "pending", "rejected", "approved_limited", "research"):
            with self.subTest(status=status):
                row = self.evidence(source="web_search", review=status)
                self.assert_visible(False)
                row.delete()

    def test_pending_manual_evidence_does_not_support(self):
        self.evidence(review="pending")
        self.assert_visible(False)

    def test_negative_evidence_does_not_support_positive_confirmation(self):
        self.evidence(polarity="negative")
        self.assert_visible(False)

    def test_other_tag_or_place_cannot_support_confirmation(self):
        other_tag = Tag.objects.create(name="콘센트있음")
        self.evidence(tag=other_tag)
        other = Place.objects.create(
            name="다른 지점", category="cafe", lat=37.6, lng=127,
            source="test", external_id="other",
        )
        self.evidence(place=other)
        self.assert_visible(False)

    def test_valid_observation_can_replace_expired_observation(self):
        self.evidence(expires_at=self.now - timedelta(days=1))
        self.evidence(source="user_feedback", review="approved")
        self.assert_visible(True)

    def test_expiry_boundary_is_excluded(self):
        self.evidence(expires_at=self.now)
        self.assert_visible(False)

    def test_confirmed_flag_cannot_bypass_support_without_is_verified(self):
        self.confirmation.is_verified = False
        self.confirmation.save()
        self.assert_visible(False)

    def test_other_confirmation_sources_keep_existing_behavior(self):
        self.confirmation.source = "field_rule"
        self.confirmation.save()
        self.assert_visible(True)

    def test_stale_tag_does_not_hide_valid_tag_of_same_name(self):
        PlaceTag.objects.create(
            place=self.place, tag=self.tag, source="field_rule",
            status="confirmed", is_verified=True,
        )
        self.assert_visible(True)

    def test_prefetch_checks_multiple_places_without_per_tag_queries(self):
        self.evidence()
        other = Place.objects.create(
            name="오래된 지점", category="cafe", lat=37.6, lng=127,
            source="test", external_id="prefetch",
        )
        PlaceTag.objects.create(
            place=other, tag=self.tag, source="user_verified",
            status="confirmed", is_verified=True,
        )
        with self.assertNumQueries(2):
            places = list(Place.objects.order_by("id").prefetch_related(Prefetch(
                "place_tags", queryset=confirmation_aware_place_tags(),
            )))
            for place in places:
                expected = place.pk == self.place.pk
                self.assertEqual(self.tag.name in get_place_tag_data(place)["verified_tags"], expected)
                self.assertEqual(self.tag.name in _db_tag_lists(place)["verified"], expected)
