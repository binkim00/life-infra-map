from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.external_place_identity import lookup_internal_place
from recommendations.services.ai_search_orchestrator import (
    _dedupe_candidates,
    _evidenced_required_place_ids,
    attach_internal_place_identity,
)
from recommendations.services.search_hard_gate import apply_common_hard_gate


class ExternalPlaceIdentityTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="모래 카페 서면점", category="cafe", address="부산 부산진구 서면로 17",
            lat=35.155, lng=129.06, source="kakao_local", external_id="12345",
        )

    def test_exact_kakao_id_still_requires_full_identity(self):
        candidate = {
            "candidate_source": "kakao", "external_id": "12345",
            "name": "모래 카페 서면점", "address": "부산 부산진구 서면로 17",
            "lat": 35.155, "lng": 129.06,
        }
        place, status = lookup_internal_place(candidate)
        self.assertEqual(place.id, self.place.id)
        self.assertEqual(status, "exact_external_id_and_identity")
        place, _ = lookup_internal_place({**candidate, "name": "모래 카페 해운대점"})
        self.assertIsNone(place)

    def test_nearby_same_name_with_conflicting_address_does_not_join(self):
        place, status = lookup_internal_place({
            "candidate_source": "kakao", "name": "모래 카페 서면점",
            "address": "부산 부산진구 다른로 20", "lat": 35.155, "lng": 129.06,
        })
        self.assertIsNone(place)
        self.assertEqual(status, "no_match")

    def test_web_without_address_and_coordinates_stays_unmatched(self):
        place, status = lookup_internal_place({
            "candidate_source": "web", "name": "모래 카페 서면점",
        })
        self.assertIsNone(place)
        self.assertEqual(status, "insufficient_identity")

    def test_two_nearby_exact_records_remain_ambiguous(self):
        Place.objects.create(
            name=self.place.name, category="cafe", address=self.place.address,
            lat=35.15501, lng=129.06001, source="other", external_id="different-record",
        )
        place, status = lookup_internal_place({
            "candidate_source": "kakao", "name": self.place.name,
            "address": self.place.address, "lat": 35.155, "lng": 129.06,
        })
        self.assertIsNone(place)
        self.assertEqual(status, "ambiguous")

    def test_saturated_nearby_window_cannot_claim_unique_identity(self):
        Place.objects.bulk_create([
            Place(name=f"다른 장소 {index}", category="cafe", lat=35.155, lng=129.06, source="test", external_id=str(index))
            for index in range(100)
        ])
        place, status = lookup_internal_place({"name": self.place.name,
            "address": self.place.address, "lat": 35.155, "lng": 129.06})
        self.assertIsNone(place)
        self.assertEqual(status, "ambiguous")

    def test_invalid_coordinates_cannot_bypass_exact_external_id(self):
        for lat, lng in ((float("nan"), 129.06), (91, 129.06), (35.155, None)):
            place, status = lookup_internal_place({"candidate_source": "kakao", "external_id": "12345",
                "name": self.place.name, "address": self.place.address, "lat": lat, "lng": lng})
            self.assertIsNone(place)
            self.assertEqual(status, "invalid_coordinates")

    def test_web_candidate_passes_strict_gate_only_after_exact_internal_join(self):
        tag = Tag.objects.create(name="조용함")
        PlaceTagEvidence.objects.create(
            place=self.place, tag=tag, source="field_rule", polarity="positive",
            source_reference="official:quiet", confidence=90,
        )
        frame = {"candidate_category_codes": ["cafe"], "required_features": ["조용함"]}
        web = {"id": "web:one", "candidate_source": "web", "name": self.place.name,
               "category": "cafe", "address": self.place.address}
        linked, statuses = attach_internal_place_identity([web], frame)
        self.assertEqual(statuses["exact_identity"], 1)
        kept, removed, _ = apply_common_hard_gate(linked, "부산 카페", frame)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])
        unmatched, _ = attach_internal_place_identity([
            {**web, "id": "web:two", "address": "부산 부산진구 다른로 20"},
        ], frame)
        kept, removed, _ = apply_common_hard_gate(unmatched, "부산 카페", frame)
        self.assertEqual(kept, [])
        self.assertEqual(len(removed), 1)

    @override_settings(EXTERNAL_PLACE_IDENTITY_ENABLED=True)
    def test_dedupe_does_not_assign_internal_identity_to_unmatched_external_candidate(self):
        candidates = _dedupe_candidates([
            {"id": f"db:{self.place.id}", "place_id": self.place.id,
             "name": self.place.name, "address": self.place.address},
            {"id": "kakao:unmatched", "candidate_source": "kakao",
             "name": self.place.name, "address": self.place.address},
        ])
        self.assertEqual(len(candidates), 2)
        self.assertIsNone(candidates[1].get("place_id"))

    def test_active_raw_evidence_retrieval_respects_each_required_tag(self):
        quiet = Tag.objects.create(name="조용함")
        outlet = Tag.objects.create(name="콘센트있음")
        for tag in (quiet, outlet):
            PlaceTagEvidence.objects.create(
                place=self.place, tag=tag, source="official", polarity="positive",
                expires_at=timezone.now() + timedelta(days=2),
            )
        bounds = {"lat_min": 35.14, "lat_max": 35.17,
                  "lng_min": 129.05, "lng_max": 129.07}
        frame = {"required_features": ["조용함", "콘센트있음"]}
        found = _evidenced_required_place_ids(
            frame, ["cafe"], bounds, 35.15, 129.06, 5,
        )
        self.assertEqual(found, [self.place.id])
        PlaceTagEvidence.objects.filter(place=self.place, tag=outlet).update(
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(_evidenced_required_place_ids(
            frame, ["cafe"], bounds, 35.15, 129.06, 5,
        ), [])
