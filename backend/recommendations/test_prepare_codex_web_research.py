from collections import Counter
from datetime import date

from django.test import TestCase

from recommendations.management.commands.prepare_codex_web_research import (
    MAX_SOURCE_HINTS,
    allocate_corroboration_quotas,
    corroboration_tags,
    order_missing_tags,
    mixed_research_selection,
    prefer_source_ready,
    preflight_source_hints,
    research_priority,
    seed_row,
    source_hints_for_places,
    select_places,
)
from recommendations.models import (
    Place, PlaceTagCollectionJob, PlaceTagEvidence, Tag, TagEnrichmentRequest,
)


class PrepareCodexWebResearchTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name="서면 연구카페",
            category="cafe",
            address="부산광역시 부산진구 중앙대로 1",
            lat=35.1579,
            lng=129.0592,
            source="semas",
            external_id="codex-research-seed",
        )

    def test_research_priority_prefers_ready_launch_then_ready_coverage_then_cold_launch(self):
        ready_launch = type("Candidate", (), {
            "id": 1, "identity_success": True, "evidence_success": True,
            "no_tag": False, "name": "ready launch",
        })()
        ready_coverage = type("Candidate", (), {
            "id": 2, "identity_success": True, "evidence_success": False,
            "no_tag": False, "name": "ready coverage",
        })()
        cold_launch = type("Candidate", (), {
            "id": 3, "identity_success": False, "evidence_success": False,
            "no_tag": True, "name": "cold launch",
        })()
        demands = {1: {"분위기좋음": 10}, 3: {"조용함": 100}}

        ordered = sorted(
            [cold_launch, ready_coverage, ready_launch],
            key=lambda place: research_priority(place, demands),
        )

        self.assertEqual([place.id for place in ordered], [1, 2, 3])

    def test_daily_corroboration_quota_is_split_across_categories(self):
        quotas = allocate_corroboration_quotas(
            {"cafe": 25, "restaurant": 25}, 25,
        )

        self.assertEqual(quotas, {"cafe": 13, "restaurant": 12})

    def test_mixed_selection_fills_missing_corroboration_with_discovery(self):
        corroboration = [{"id": 1}, {"id": 2}]
        discovery = [{"id": value} for value in range(3, 10)]

        selected = mixed_research_selection(
            corroboration, discovery, limit=6, corroboration_limit=3,
        )

        self.assertEqual(len(selected), 6)
        self.assertEqual([row["id"] for row in selected], [1, 2, 3, 4, 5, 6])

    def test_mixed_selection_fills_missing_discovery_with_corroboration(self):
        corroboration = [{"id": value} for value in range(1, 7)]
        discovery = [{"id": 7}]

        selected = mixed_research_selection(
            corroboration, discovery, limit=5, corroboration_limit=2,
        )

        self.assertEqual(len(selected), 5)
        self.assertEqual([row["id"] for row in selected], [1, 2, 7, 3, 4])

    def test_database_selection_reserves_one_corroboration_and_one_discovery_place(self):
        discovery = Place.objects.create(
            name="서면 신규카페",
            category="cafe",
            address="부산광역시 부산진구 중앙대로 2",
            lat=35.1580,
            lng=129.0593,
            source="semas",
            external_id="codex-research-discovery",
        )
        for index, place in enumerate((self.place, discovery), start=1):
            PlaceTagCollectionJob.objects.create(
                place=place,
                provider="naver_search",
                cycle_date=date(2026, 9, index),
                status="completed",
                stats={"diagnostics": {"identity_matches": 1}},
            )
        tag = Tag.objects.create(name="조용함")
        PlaceTagEvidence.objects.create(
            place=self.place,
            tag=tag,
            source="web_search",
            source_reference="https://one.example/quiet",
            polarity="positive",
            evidence="조용한 카페",
        )

        selected = select_places("cafe", 2, Counter(), corroboration_limit=1)

        self.assertEqual(Counter(row["research_track"] for row in selected), {
            "corroboration": 1,
            "discovery": 1,
        })

    def test_source_hints_reuse_only_identity_matched_public_urls(self):
        PlaceTagCollectionJob.objects.create(
            place=self.place,
            provider="naver_search",
            cycle_date=date(2026, 8, 25),
            status="completed",
            stats={
                "diagnostics": {"identity_matches": 2},
                "search_attempts": [{
                    "results": [
                        {
                            "url": "https://blog.example.com/right-place",
                            "title": "서면 연구카페 방문기",
                            "description": "좌석과 분위기를 소개한다.",
                            "identity_matched": True,
                        },
                        {
                            "url": "https://blog.example.com/wrong-place",
                            "identity_matched": False,
                        },
                    ],
                }],
            },
        )

        hints = source_hints_for_places([self.place.id])

        self.assertEqual(len(hints[self.place.id]), 1)
        self.assertEqual(hints[self.place.id][0]["url"], "https://blog.example.com/right-place")
        self.assertLessEqual(len(hints[self.place.id]), MAX_SOURCE_HINTS)

    def test_source_hints_prioritize_existing_verified_evidence_urls(self):
        tag = Tag.objects.create(name="stored-source-tag")
        PlaceTagEvidence.objects.create(
            place=self.place,
            tag=tag,
            source="naver_blog_search",
            source_reference="https://blog.example.com/stored-page",
            evidence="stored snippet",
            context={"source_title": "stored title"},
        )

        hints = source_hints_for_places([self.place.id])

        self.assertEqual(hints[self.place.id][0]["url"], "https://blog.example.com/stored-page")
        self.assertEqual(hints[self.place.id][0]["hint_origin"], "stored_evidence")

    def test_source_hints_exclude_naver_blog_pages_codex_cannot_revalidate(self):
        tag = Tag.objects.create(name="naver-source-tag")
        PlaceTagEvidence.objects.create(
            place=self.place,
            tag=tag,
            source="naver_blog_search",
            source_reference="https://blog.naver.com/example/123",
            evidence="search snippet only",
        )

        hints = source_hints_for_places([self.place.id])

        self.assertEqual(hints[self.place.id], [])

    def test_source_hints_reuse_page_unavailable_retry_candidates(self):
        TagEnrichmentRequest.objects.create(
            place=self.place,
            tag_name="조용함",
            status="queued",
            context={
                "codex_candidate_research": {
                    "sources": [{
                        "url": "https://reviews.example.com/retry",
                        "title": "서면 연구카페 후기",
                        "snippet": "조용하다는 검색 결과 문구",
                    }],
                },
            },
        )

        hints = source_hints_for_places([self.place.id])

        self.assertEqual(hints[self.place.id][0]["url"], "https://reviews.example.com/retry")
        self.assertEqual(hints[self.place.id][0]["hint_origin"], "page_unavailable_retry")

    def test_prefer_source_ready_fills_reachable_rows_first(self):
        cold = {"place": self.place, "source_hints": []}
        ready = {"place": self.place, "source_hints": [{"url": "https://example.com"}]}

        selected = prefer_source_ready([cold, ready], 1)

        self.assertEqual(selected, [ready])

    def test_prefer_source_ready_keeps_reachable_coverage_ahead_of_unreachable_retry(self):
        retry = {
            "place": self.place,
            "source_hints": [],
            "launch_demand": {"조용함": 11},
        }
        coverage = {
            "place": self.place,
            "source_hints": [{"url": "https://example.com"}],
            "launch_demand": {},
        }

        selected = prefer_source_ready([coverage, retry], 1)

        self.assertEqual(selected, [coverage])

    def test_missing_tags_prioritize_researchability_before_forced_diversity(self):
        ordered = order_missing_tags(
            ["유모차접근", "분위기좋음", "사진찍기좋음"],
            category="cafe",
            demand={},
            allocation={
                ("cafe", "유모차접근"): 0,
                ("cafe", "분위기좋음"): 10,
                ("cafe", "사진찍기좋음"): 0,
            },
            category_tags=["분위기좋음", "사진찍기좋음", "유모차접근"],
        )

        self.assertEqual(ordered, ["분위기좋음", "사진찍기좋음", "유모차접근"])

    def test_launch_demand_still_overrides_researchability(self):
        ordered = order_missing_tags(
            ["분위기좋음", "유모차접근"],
            category="restaurant",
            demand={"유모차접근": 50},
            allocation={("restaurant", "분위기좋음"): 0, ("restaurant", "유모차접근"): 0},
            category_tags=["분위기좋음", "유모차접근"],
        )

        self.assertEqual(ordered[0], "유모차접근")

    def test_single_positive_web_source_is_prioritized_for_corroboration(self):
        observations = [
            {
                "tag_name": "콘센트있음", "polarity": "positive",
                "source": "web_search", "source_reference": "https://one.example/cafe",
            },
            {
                "tag_name": "분위기좋음", "polarity": "positive",
                "source": "field_rule", "source_reference": "field:category",
            },
        ]

        corroboration = corroboration_tags(observations)
        ordered = order_missing_tags(
            ["분위기좋음", "콘센트있음"],
            category="cafe",
            demand={},
            allocation={("cafe", "분위기좋음"): 0, ("cafe", "콘센트있음"): 0},
            category_tags=["분위기좋음", "콘센트있음"],
            corroboration=corroboration,
        )

        self.assertEqual(corroboration, ["콘센트있음"])
        self.assertEqual(ordered[0], "콘센트있음")

    def test_conflicted_or_already_independent_tags_do_not_need_corroboration(self):
        rows = [
            {"tag_name": "조용함", "polarity": "positive", "source": "web_search", "source_reference": "https://one.example"},
            {"tag_name": "조용함", "polarity": "negative", "source": "naver_blog_search", "source_reference": "https://two.example"},
            {"tag_name": "데이트좋음", "polarity": "positive", "source": "web_search", "source_reference": "https://three.example"},
            {"tag_name": "데이트좋음", "polarity": "positive", "source": "naver_blog_search", "source_reference": "https://four.example"},
        ]

        self.assertEqual(corroboration_tags(rows), [])

    def test_seed_exposes_multiple_missing_tags_and_source_hints(self):
        row = seed_row({
            "place": self.place,
            "tag": "분위기좋음",
            "target_tags": ["분위기좋음", "사진찍기좋음", "조용함"],
            "active_tags": ["콘센트있음"],
            "source_hints": [{"url": "https://blog.example.com/right-place"}],
            "corroboration_tags": ["분위기좋음"],
        })

        self.assertEqual(row["target_tag"], "분위기좋음")
        self.assertEqual(row["target_tags"], ["분위기좋음", "사진찍기좋음", "조용함"])
        self.assertIn("감성적인", row["target_tag_search_terms"]["분위기좋음"])
        self.assertEqual(row["corroboration_tags"], ["분위기좋음"])
        self.assertEqual(row["source_hints"][0]["url"], "https://blog.example.com/right-place")
        self.assertEqual(row["candidate_sources"], [])
        self.assertEqual(row["failure_detail"], "")

    def test_preflight_keeps_only_pages_readable_by_production_fetcher(self):
        selected = [{
            "place": self.place,
            "source_hints": [
                {"url": "https://blog.example.com/readable", "title": "old"},
                {"url": "https://blog.example.com/blocked", "title": "blocked"},
            ],
        }]

        def fetcher(url):
            if url.endswith("readable"):
                return {"ok": True, "url": url, "title": "verified title"}
            return {"ok": False, "error": "ROBOTS_DENIED"}

        stats = preflight_source_hints(selected, fetcher=fetcher)

        self.assertEqual(stats, {"checked": 2, "reachable": 1, "rejected": 1})
        self.assertEqual(len(selected[0]["source_hints"]), 1)
        self.assertTrue(selected[0]["source_hints"][0]["preflight_verified"])
