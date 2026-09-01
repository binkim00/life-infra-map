import unittest

from render_daily_report import render_report


def metric(value, numerator, denominator):
    return {"measured": True, "value": value, "numerator": numerator, "denominator": denominator}


class RenderDailyReportTests(unittest.TestCase):
    def test_report_explains_saved_candidates_and_quality_gate(self):
        payload = {
            "collection": {
                "date": "2026-09-01", "generated_at": "2026-09-01T06:00:00Z",
                "naver": {"planned_jobs": 10, "completed_jobs": 10, "useful_jobs": 4, "insufficient_jobs": 6, "failed_jobs": 0, "api_requests": 20, "rate_limited_requests": 0, "new_evidence_rows": 4, "new_evidence_places": 3, "new_evidence_tags": 4},
                "codex_web": {"new_evidence_rows": 7, "new_evidence_places": 5},
                "aggregate_tags": {"new_place_tags": 8, "new_tagged_places": 6},
            },
            "codex_runs": {"window_start": "2026-08-31T06:00:00Z", "runs": 2, "rows": 12, "accepted": 1, "needs_verification": 6, "candidate_pending": 2, "candidates_preserved": 2, "rejected": 3, "saved": 7, "primary_saved": 5, "related_saved": 2, "reasons": {}},
            "quality": {
                "daily_delta": {"cafe_searchable_places": 2, "restaurant_searchable_places": 1},
                "search": {
                    "top_five_coverage_rate": metric(1, 24, 24), "feature_query_hit_at_5_rate": metric(0.2, 4, 20), "verified_feature_result_rate_at_5": metric(0.05, 5, 100), "honest_no_hit_fallback_rate": metric(1, 20, 20), "reason_transparency_rate": metric(1, 120, 120), "hard_violation_rate": metric(0, 0, 120), "latency_ms": {"measured": True, "value": {"average": 1100.5, "p95": 2689.5}},
                },
                "release_gate": {"ready": False, "consecutive_ready_days": 0, "thresholds": {"top_five_coverage_rate": 1, "feature_query_hit_at_5_rate": 1, "verified_feature_result_rate_at_5_min": 0.6, "reason_transparency_rate": 1, "hard_violation_rate_max": 0, "latency_p95_ms_max": 3000}},
            },
        }
        rendered = render_report(payload)
        self.assertIn("판정(즉시 확정 가능/확인 필요/재조사/탈락): 1 / 6 / 2 / 3개", rendered)
        self.assertIn("DB에 근거 후보로 저장: 7개", rendered)
        self.assertIn("집계 시작: 2026-08-31T06:00:00Z", rendered)
        self.assertIn("검색마다 상위 5개 제공: 100.0% (24 / 24)", rendered)
        self.assertIn("검색 속도: 평균 1100.5ms, p95 2689.5ms", rendered)
        failures = rendered.split("현재 미충족 항목:", 1)[1]
        self.assertIn("각 조건 검색에 검증 근거 결과 포함", failures)
        self.assertIn("상위 5개 검증 근거 비율", failures)
        self.assertNotIn("검색 속도 p95", failures)


if __name__ == "__main__":
    unittest.main()
