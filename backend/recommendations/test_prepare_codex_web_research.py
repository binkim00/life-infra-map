from datetime import date

from django.test import TestCase

from recommendations.management.commands.prepare_codex_web_research import (
    MAX_SOURCE_HINTS,
    prefer_source_ready,
    preflight_source_hints,
    research_priority,
    seed_row,
    source_hints_for_places,
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

    def test_prefer_source_ready_keeps_unreachable_retry_ahead_of_coverage(self):
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

        self.assertEqual(selected, [retry])

    def test_seed_exposes_multiple_missing_tags_and_source_hints(self):
        row = seed_row({
            "place": self.place,
            "tag": "분위기좋음",
            "target_tags": ["분위기좋음", "사진찍기좋음", "조용함"],
            "active_tags": ["콘센트있음"],
            "source_hints": [{"url": "https://blog.example.com/right-place"}],
        })

        self.assertEqual(row["target_tag"], "분위기좋음")
        self.assertEqual(row["target_tags"], ["분위기좋음", "사진찍기좋음", "조용함"])
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
