from datetime import date

from django.test import TestCase

from recommendations.management.commands.prepare_codex_web_research import (
    MAX_SOURCE_HINTS,
    preflight_source_hints,
    seed_row,
    source_hints_for_places,
)
from recommendations.models import Place, PlaceTagCollectionJob


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
