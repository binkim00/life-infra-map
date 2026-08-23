from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.search_hard_gate import apply_common_hard_gate


class CommonSearchHardGateTests(TestCase):
    def setUp(self):
        self.cafe = Place.objects.create(
            name="근거 카페",
            category="cafe",
            address="서울특별시 강남구",
            lat=37.5,
            lng=127.0,
            source="test",
            external_id="hard-gate-cafe",
        )
        self.parking_tag = Tag.objects.create(name="주차가능")

    def _candidate(self, place=None, **extra):
        place = place or self.cafe
        return {
            "id": f"db:{place.id}",
            "candidate_source": "db",
            "place_id": place.id,
            "name": place.name,
            "category": place.category,
            "address": place.address,
            **extra,
        }

    def test_unknown_objective_feature_is_rejected(self):
        kept, removed, debug = apply_common_hard_gate(
            [self._candidate()], "주차 가능한 카페", {},
        )
        self.assertEqual(kept, [])
        self.assertEqual(len(removed), 1)
        self.assertEqual(debug["removed_by_type"], {"feature": 1})
        self.assertEqual(
            removed[0]["hard_gate_violations"][0]["evidence_status"],
            "unknown",
        )

    def test_active_negative_feature_is_marked_contradicted(self):
        PlaceTagEvidence.objects.create(
            place=self.cafe,
            tag=self.parking_tag,
            source="field_rule",
            polarity="negative",
            confidence=90,
            expires_at=timezone.now() + timedelta(days=1),
        )

        kept, removed, _ = apply_common_hard_gate(
            [self._candidate()], "주차 가능한 카페", {},
        )

        self.assertEqual(kept, [])
        self.assertEqual(
            removed[0]["hard_gate_violations"][0]["evidence_status"],
            "contradicted",
        )

    def test_semantic_document_feature_cannot_satisfy_hard_gate_without_current_evidence(self):
        candidate = self._candidate(
            candidate_source="semantic",
            retrieval_semantic_features=["주차가능"],
        )
        kept, removed, _ = apply_common_hard_gate(
            [candidate], "주차 가능한 카페", {},
        )
        self.assertEqual(kept, [])
        self.assertEqual(removed[0]["hard_gate_active_tags"], [])

    def test_active_positive_feature_passes_but_stale_does_not(self):
        evidence = PlaceTagEvidence.objects.create(
            place=self.cafe,
            tag=self.parking_tag,
            source="field_rule",
            polarity="positive",
            confidence=90,
            expires_at=timezone.now() + timedelta(days=1),
        )
        kept, _, _ = apply_common_hard_gate(
            [self._candidate()], "주차 가능한 카페", {},
        )
        self.assertEqual(len(kept), 1)

        evidence.expires_at = timezone.now() - timedelta(seconds=1)
        evidence.save(update_fields=["expires_at"])
        kept, removed, _ = apply_common_hard_gate(
            [self._candidate()], "주차 가능한 카페", {},
        )
        self.assertEqual(kept, [])
        self.assertEqual(len(removed), 1)

    def test_explicit_category_applies_to_every_candidate_source(self):
        for source in ("db", "kakao", "fallback", "semantic"):
            candidate = {
                "id": f"{source}:1",
                "candidate_source": source,
                "name": "다른 후보",
                "category": "음식점 > 한식",
                "address": "서울특별시 강남구",
            }
            kept, removed, debug = apply_common_hard_gate(
                [candidate], "조용한 카페", {},
            )
            self.assertEqual(kept, [], source)
            self.assertEqual(debug["removed_by_source"], {source: 1})
            self.assertEqual(
                removed[0]["hard_gate_violations"][0]["type"], "category",
            )

    def test_explicit_region_rejects_other_region(self):
        candidate = self._candidate(address="부산광역시 부산진구")
        kept, removed, _ = apply_common_hard_gate([candidate], "서울 카페", {})
        self.assertEqual(kept, [])
        self.assertEqual(removed[0]["hard_gate_violations"][0]["type"], "region")

    def test_freewifi_category_satisfies_free_wifi_without_becoming_free_use(self):
        place = Place.objects.create(
            name="공공 와이파이",
            category="freewifi",
            address="서울특별시 중구",
            lat=37.5,
            lng=127.0,
            source="test",
            external_id="hard-gate-wifi",
        )
        kept, removed, _ = apply_common_hard_gate(
            [self._candidate(place)], "무료 와이파이 되는 곳", {},
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])

    def test_pharmacy_name_repairs_stale_source_category_but_rejects_cafe(self):
        pharmacy = self._candidate(
            name="서면365약국",
            category="tourism",
        )
        cafe = self._candidate(
            name="하삼동커피 문현현대점",
            category="cafe",
        )

        kept, removed, _ = apply_common_hard_gate(
            [pharmacy, cafe], "가까운 약국", {},
        )

        self.assertEqual([row["name"] for row in kept], ["서면365약국"])
        self.assertEqual(kept[0]["category"], "pharmacy")
        self.assertEqual(kept[0]["source_category"], "tourism")
        self.assertEqual([row["name"] for row in removed], ["하삼동커피 문현현대점"])

    def test_open_now_and_work_cafe_require_current_evidence(self):
        pharmacy = self._candidate(name="행복한약국", category="tourism")
        kept, removed, _ = apply_common_hard_gate(
            [pharmacy], "지금 문 연 약국", {},
        )
        self.assertEqual(kept, [])
        self.assertEqual(removed[0]["category"], "pharmacy")
        self.assertEqual(
            removed[0]["hard_gate_violations"][0]["required"],
            "open_now",
        )

        kept, removed, _ = apply_common_hard_gate(
            [self._candidate()], "작업할 카페", {},
        )
        self.assertEqual(kept, [])
        self.assertEqual(
            removed[0]["hard_gate_violations"][0]["required"],
            "work_friendly",
        )
