from django.test import SimpleTestCase

from recommendations.services.ai_search_orchestrator import (
    _diversify_ordered_results,
    _result_building_key,
)


def _candidate(candidate_id, *, name, address, tier=0, matched=1):
    return {
        "id": candidate_id,
        "name": name,
        "address": address,
        "category": "cafe",
        "result_quality_sort_key": tier,
        "condition_match_count": matched,
    }


class ResultDiversityTests(SimpleTestCase):
    frame = {
        "candidate_category_codes": ["cafe"],
        "constraints": ["조용함", "작업하기 좋음"],
    }

    def test_building_key_ignores_floor_and_unit_details(self):
        first = _candidate(
            "a",
            name="카페 A",
            address="부산 부산진구 중앙대로 672 1층 101호",
        )
        second = _candidate(
            "b",
            name="카페 B",
            address="부산 부산진구 중앙대로 672 지하 1층",
        )

        self.assertEqual(_result_building_key(first), _result_building_key(second))

    def test_distinct_buildings_are_promoted_inside_same_quality_stratum(self):
        candidates = [
            _candidate("a1", name="카페 A1", address="부산 중앙대로 672 1층"),
            _candidate("a2", name="카페 A2", address="부산 중앙대로 672 2층"),
            _candidate("a3", name="카페 A3", address="부산 중앙대로 672 3층"),
            _candidate("b", name="카페 B", address="부산 중앙대로 680"),
            _candidate("c", name="카페 C", address="부산 중앙대로 690"),
        ]

        diversified = _diversify_ordered_results(candidates, self.frame, limit=5)

        self.assertEqual([item["id"] for item in diversified], ["a1", "b", "c", "a2", "a3"])

    def test_same_franchise_does_not_monopolize_top_results(self):
        candidates = [
            _candidate("s1", name="스타벅스 서면점", address="부산 중앙대로 670"),
            _candidate("s2", name="스타벅스 전포점", address="부산 중앙대로 680"),
            _candidate("s3", name="스타벅스 부전점", address="부산 중앙대로 690"),
            _candidate("local", name="로컬커피", address="부산 중앙대로 700"),
        ]

        diversified = _diversify_ordered_results(candidates, self.frame, limit=4)

        self.assertEqual([item["id"] for item in diversified], ["s1", "s2", "local", "s3"])

    def test_quality_strata_remain_a_hard_ordering_boundary(self):
        candidates = [
            _candidate("strict1", name="카페 A1", address="부산 중앙대로 672 1층"),
            _candidate("strict2", name="카페 A2", address="부산 중앙대로 672 2층"),
            _candidate("partial", name="카페 B", address="부산 중앙대로 680", tier=1),
        ]

        diversified = _diversify_ordered_results(candidates, self.frame, limit=3)

        self.assertEqual(
            [item["id"] for item in diversified],
            ["strict1", "strict2", "partial"],
        )

    def test_explicit_nearest_request_keeps_original_distance_order(self):
        candidates = [
            _candidate("a1", name="카페 A1", address="부산 중앙대로 672 1층"),
            _candidate("a2", name="카페 A2", address="부산 중앙대로 672 2층"),
            _candidate("b", name="카페 B", address="부산 중앙대로 680"),
        ]
        nearest_frame = {
            **self.frame,
            "constraints": ["가장 가까운"],
        }

        diversified = _diversify_ordered_results(candidates, nearest_frame, limit=3)

        self.assertEqual([item["id"] for item in diversified], ["a1", "a2", "b"])
