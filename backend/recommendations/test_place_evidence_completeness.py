from django.test import TestCase
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.bootstrap_priority import priority_context
from recommendations.services.place_evidence_completeness import (
    assess_evidence_quality,
    target_tags_for_gaps,
)


def observation(tag, *, polarity="positive", source="naver_blog_search", reference=None):
    return {
        "tag_name": tag,
        "polarity": polarity,
        "source": source,
        "source_reference": reference or f"https://example.com/{tag}",
    }


class PlaceEvidenceCompletenessUnitTests(TestCase):
    def test_basic_facts_do_not_make_place_recommendation_ready(self):
        profile = assess_evidence_quality("cafe", [
            observation("카페"),
            observation("무료와이파이"),
            observation("주차가능"),
        ])

        self.assertEqual(profile["level"], "empty")
        self.assertEqual(profile["meaningful_tag_count"], 0)
        self.assertEqual(profile["dimension_count"], 0)

    def test_multiple_experience_dimensions_make_place_searchable(self):
        profile = assess_evidence_quality("cafe", [
            observation("조용함", reference="https://example.com/one"),
            observation("노트북작업", reference="https://example.com/two"),
            observation("콘센트있음", reference="https://example.com/two"),
        ])

        self.assertEqual(profile["level"], "searchable")
        self.assertEqual(profile["dimension_count"], 2)
        self.assertEqual(profile["source_count"], 2)

    def test_rich_profile_requires_tradeoff_evidence(self):
        rows = [
            observation("조용함", reference="https://example.com/one"),
            observation("노트북작업", reference="https://example.com/two"),
            observation("콘센트있음", reference="https://example.com/two"),
            observation("좌석간격넓음", reference="https://example.com/three"),
            observation("혼자이용좋음", reference="https://example.com/three"),
            observation("주차어려움", polarity="positive", reference="https://example.com/four"),
        ]

        profile = assess_evidence_quality("cafe", rows)

        self.assertEqual(profile["level"], "rich")
        self.assertTrue(profile["has_tradeoff_evidence"])

    def test_one_found_feature_still_targets_unknown_dimensions(self):
        targets = target_tags_for_gaps("cafe", [observation("조용함")], limit=30)

        self.assertIn("노트북작업", targets)
        self.assertIn("좌석간격넓음", targets)
        self.assertIn("혼자이용좋음", targets)
        self.assertIn("전망좋음", targets)
        self.assertIn("주차어려움", targets)


class PlaceEvidenceCompletenessPlannerTests(TestCase):
    def test_basic_evidence_does_not_close_planner_gap(self):
        place = Place.objects.create(
            name="기본 정보만 있는 카페",
            category="cafe",
            address="부산광역시 부산진구 중앙대로 1",
            lat=35.16,
            lng=129.06,
            source="kakao_local",
            external_id="quality-gap-cafe",
        )
        basic_tag = Tag.objects.create(name="카페", tag_type="category")
        PlaceTagEvidence.objects.create(
            place=place,
            tag=basic_tag,
            source="field_rule",
            source_reference="official-row",
            polarity="positive",
            observed_at=timezone.now(),
        )

        context = priority_context([place])[place.id]

        self.assertEqual(context["recommendation_evidence_quality"]["level"], "empty")
        self.assertEqual(context["active_tag_count"], 0)
        self.assertEqual(context["adaptive_reason"], "evidence_dimension_gap")
        self.assertIn("노트북작업", context["targeted_tags"])

    def test_thin_place_gets_launch_cohort_depth_priority(self):
        empty_place = Place.objects.create(
            name="새 카페",
            category="cafe",
            address="부산광역시 동구 중앙대로 2",
            lat=35.17,
            lng=129.05,
            source="kakao_local",
            external_id="empty-cafe",
        )
        thin_place = Place.objects.create(
            name="단서가 있는 카페",
            category="cafe",
            address="부산광역시 동구 중앙대로 3",
            lat=35.18,
            lng=129.04,
            source="kakao_local",
            external_id="thin-cafe",
        )
        tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        PlaceTagEvidence.objects.create(
            place=thin_place,
            tag=tag,
            source="naver_blog_search",
            source_reference="https://example.com/quiet",
            polarity="positive",
            observed_at=timezone.now(),
        )

        contexts = priority_context([empty_place, thin_place])

        self.assertEqual(
            contexts[empty_place.id]["components"]["recommendation_depth_priority"], 12
        )
        self.assertEqual(
            contexts[thin_place.id]["components"]["recommendation_depth_priority"], 30
        )
        self.assertIn("노트북작업", contexts[thin_place.id]["targeted_tags"])
