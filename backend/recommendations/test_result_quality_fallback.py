from django.test import SimpleTestCase, TestCase

from recommendations.models import Place
from recommendations.services.ai_search_orchestrator import (
    _collect_derived_shopping_candidates,
    _complete_and_order_results,
)


class ResultQualityFallbackTests(SimpleTestCase):
    def _candidate(self, index, *, verified=None, violations=None, level="weak"):
        return {
            "id": f"db:{index}",
            "candidate_source": "db",
            "name": f"후보 카페 {index}",
            "category": "cafe",
            "address": "부산광역시 부산진구",
            "distance": index * 100,
            "score": 80 - index,
            "pre_ai_evidence_level": level,
            "verified_tags": verified or [],
            "hard_gate_violations": violations or [],
            "pre_ai_unmet_constraints": [],
        }

    def _frame(self):
        return {
            "candidate_category_codes": ["cafe"],
            "constraints": ["조용함", "콘센트"],
        }

    def test_returns_more_than_five_and_orders_by_condition_coverage(self):
        full = self._candidate(1, verified=["조용함", "콘센트"], level="strong")
        partial = self._candidate(2, verified=["조용함"], level="medium")
        pool = [full, partial, *(self._candidate(index) for index in range(3, 8))]

        results, additions = _complete_and_order_results(
            [partial, full], pool, [], [], self._frame(), limit=7,
        )

        self.assertEqual(len(results), 7)
        self.assertEqual(len(additions), 5)
        self.assertEqual(results[0]["result_tier"], "all_conditions_met")
        self.assertEqual(results[1]["result_tier"], "partial_match")
        self.assertTrue(all(
            row["result_tier"] == "best_available" for row in results[2:]
        ))
        self.assertIn("확인된 조건은 조용함, 콘센트", results[0]["recommendation_reason"])
        self.assertIn("부족하거나 확인이 필요한 조건은 콘센트", results[1]["recommendation_reason"])

    def test_same_tier_uses_distance_before_evidence_strength_and_normalizes_category_label(self):
        far_strong = self._candidate(30, level="strong")
        near_external = self._candidate(1, level="medium")
        near_external.update({
            "id": "kakao:near",
            "candidate_source": "kakao",
            "category": "음식점 > 카페 > 커피전문점",
        })

        results, _ = _complete_and_order_results(
            [], [far_strong, near_external], [], [], self._frame(), limit=5,
        )

        self.assertEqual([row["id"] for row in results], ["kakao:near", "db:30"])
        self.assertIn("카페 후보", results[0]["recommendation_reason"])
        self.assertNotIn("음식점 >", results[0]["recommendation_reason"])

    def test_unknown_feature_can_be_disclosed_but_contradicted_feature_is_excluded(self):
        unknown = self._candidate(1, violations=[{
            "type": "feature",
            "required": "parking",
            "label": "주차가능",
            "evidence_status": "unknown",
        }])
        contradicted = self._candidate(2, violations=[{
            "type": "feature",
            "required": "parking",
            "label": "주차가능",
            "evidence_status": "contradicted",
        }])

        results, _ = _complete_and_order_results(
            [], [], [unknown, contradicted], [], self._frame(), limit=5,
        )

        self.assertEqual([row["id"] for row in results], ["db:1"])
        self.assertIn("주차가능", results[0]["missing_conditions"])
        self.assertIn("부족하거나 확인이 필요한 조건", results[0]["recommendation_reason"])

    def test_category_or_region_violation_is_never_relaxed(self):
        wrong_category = self._candidate(1, violations=[{
            "type": "category", "required": ["cafe"], "actual": ["restaurant"],
        }])
        wrong_region = self._candidate(2, violations=[{
            "type": "region", "required": "부산", "actual": "서울특별시",
        }])

        results, _ = _complete_and_order_results(
            [], [], [wrong_category, wrong_region], [], self._frame(), limit=5,
        )

        self.assertEqual(results, [])

    def test_explicit_alternative_category_can_disclose_semantic_gap(self):
        indoor_cafe = self._candidate(1)
        indoor_cafe["pre_ai_unmet_constraints"] = [
            "실내 체험 요청과 맞지 않는 후보",
        ]
        excluded_cafe = self._candidate(2)
        excluded_cafe["pre_ai_unmet_constraints"] = [
            "제외 조건과 맞지 않는 카페 정보",
        ]

        results, _ = _complete_and_order_results(
            [], [indoor_cafe, excluded_cafe], [], [], self._frame(), limit=5,
        )

        self.assertEqual([row["id"] for row in results], ["db:1"])
        self.assertIn("실내 체험 근거 확인 필요", results[0]["missing_conditions"])


class DerivedShoppingCandidateTests(TestCase):
    def test_groups_tenant_rows_into_their_parent_shopping_venue(self):
        for index, tenant in enumerate(["골든듀", "금강제화", "네스프레소"], start=1):
            Place.objects.create(
                name=f"{tenant} 롯데백화점 부산본점",
                category="tourism",
                address="부산광역시 부산진구 가야대로 772",
                lat=35.15679,
                lng=129.05642,
                source="test",
                external_id=f"shopping-tenant-{index}",
            )

        results = _collect_derived_shopping_candidates(
            lat=35.1579,
            lng=129.0592,
            limit=10,
            radius=8000,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "롯데백화점 부산본점")
        self.assertEqual(results[0]["category"], "shopping")
        self.assertEqual(results[0]["venue_evidence_count"], 3)
        self.assertTrue(results[0]["derived_from_tenant_records"])
