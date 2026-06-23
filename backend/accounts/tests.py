from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from boards.models import Comment, Post
from recommendations.models import PlaceReport

from .utils import TIER_COLORS, calculate_user_contribution, get_user_tier_info


class UserContributionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="contributor",
            password="password123",
        )
        self.client = APIClient()

    def create_post_and_comment(self):
        post = Post.objects.create(
            author=self.user,
            board_type="free",
            title="테스트 글",
            content="본문",
        )
        Comment.objects.create(
            author=self.user,
            post=post,
            content="댓글",
        )
        return post

    def test_post_and_comment_contribution_keeps_existing_score_rule(self):
        self.create_post_and_comment()

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(calculate_user_contribution(post_count=1, comment_count=1), 3)
        self.assertEqual(tier_info["contribution"], 3)
        self.assertEqual(tier_info["score"], 3)

    def test_approved_tag_suggestion_report_is_included_in_contribution(self):
        PlaceReport.objects.create(
            user=self.user,
            report_type="tag_suggestion",
            status="approved",
            description="태그 제보",
        )

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 10)

    def test_approved_new_place_report_has_higher_contribution(self):
        PlaceReport.objects.create(
            user=self.user,
            report_type="new_place",
            status="approved",
            description="새 장소 제보",
        )

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 20)

    def test_pending_and_rejected_reports_are_not_included_in_contribution(self):
        PlaceReport.objects.create(
            user=self.user,
            report_type="new_place",
            status="pending",
            description="대기 제보",
        )
        PlaceReport.objects.create(
            user=self.user,
            report_type="tag_suggestion",
            status="rejected",
            description="반려 제보",
        )

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 0)
        self.assertEqual(tier_info["score"], 0)

    def test_user_serializer_response_contains_contribution_and_nickname_color(self):
        PlaceReport.objects.create(
            user=self.user,
            report_type="tag_suggestion",
            status="approved",
            description="태그 제보",
        )
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/accounts/me/")

        self.assertEqual(response.status_code, 200)
        user_data = response.data["user"]
        self.assertEqual(user_data["contribution"], 10)
        self.assertEqual(user_data["score"], 10)
        self.assertEqual(user_data["tier"], "platinum")
        self.assertEqual(user_data["nickname_color"], TIER_COLORS["platinum"])

    def test_tier_is_calculated_from_contribution(self):
        PlaceReport.objects.create(
            user=self.user,
            report_type="new_place",
            status="approved",
            description="새 장소 제보",
        )

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 20)
        self.assertEqual(tier_info["tier"], "challenger")
        self.assertEqual(tier_info["tier_label"], "챌린저")
