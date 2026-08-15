from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from recommendations.management.commands.apply_structured_evidence_freshness import apply_freshness
from recommendations.models import Place, PlaceTag, PlaceTagEvidence, Tag
from recommendations.services.structured_evidence_freshness import freshness_state, structured_expiry


class StructuredEvidenceFreshnessTests(TestCase):
    def test_freewifi_uses_structured_source_ttl(self):
        now = timezone.now()
        self.assertEqual(
            freshness_state(now - timedelta(days=399), place_source="freewifi", now=now),
            "current",
        )
        self.assertEqual(
            freshness_state(now - timedelta(days=401), place_source="freewifi", now=now),
            "stale",
        )

    @override_settings(STRUCTURED_EVIDENCE_TTL_DAYS={"public_test": 30})
    def test_source_ttl_distinguishes_current_stale_and_unknown(self):
        now = timezone.now()
        self.assertEqual(freshness_state(now - timedelta(days=31), place_source="public_test", now=now), "stale")
        self.assertEqual(freshness_state(now - timedelta(days=29), place_source="public_test", now=now), "current")
        self.assertEqual(freshness_state(None, place_source="public_test", now=now), "unknown")
        self.assertIsNone(structured_expiry(None, place_source="public_test"))

    @override_settings(STRUCTURED_EVIDENCE_TTL_DAYS={"public_test": 30})
    def test_stale_evidence_is_kept_and_aggregate_requires_verification(self):
        now = timezone.now()
        place = Place.objects.create(name="공공시설", category="toilet", address="서울", lat=37.5, lng=127, source="public_test", external_id="1")
        tag = Tag.objects.create(name="직접태그")
        aggregate = PlaceTag.objects.create(place=place, tag=tag, source="field_rule", status="confirmed", is_verified=True)
        evidence = PlaceTagEvidence.objects.create(
            place=place, tag=tag, source="field_rule", polarity="positive",
            observed_at=now - timedelta(days=31), evidence_key="freshness-test",
        )
        report = apply_freshness(PlaceTagEvidence.objects.filter(id=evidence.id).select_related("place"), now=now)
        evidence.refresh_from_db()
        aggregate.refresh_from_db()
        self.assertEqual(report["stale"], 1)
        self.assertIsNotNone(evidence.expires_at)
        self.assertEqual(PlaceTagEvidence.objects.count(), 1)
        self.assertEqual(aggregate.status, "needs_verification")
