from unittest import skip
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
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

    def create_post(self, created_at=None):
        post = Post.objects.create(
            author=self.user,
            board_type="free",
            title="테스트 글",
            content="본문",
        )
        if created_at:
            Post.objects.filter(id=post.id).update(created_at=created_at)
        return post

    def create_comment(self, post, created_at=None):
        comment = Comment.objects.create(
            author=self.user,
            post=post,
            content="댓글",
        )
        if created_at:
            Comment.objects.filter(id=comment.id).update(created_at=created_at)
        return comment

    def test_daily_post_and_comment_contribution_uses_grouped_score_rule(self):
        post = self.create_post()
        for index in range(4):
            self.create_post()
        for index in range(10):
            self.create_comment(post)

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(calculate_user_contribution(post_count=5, comment_count=10), 2)
        self.assertEqual(tier_info["contribution"], 2)
        self.assertEqual(tier_info["score"], 2)

    def test_daily_post_and_comment_contribution_is_capped_at_five(self):
        post = self.create_post()
        for index in range(29):
            self.create_post()
        for index in range(40):
            self.create_comment(post)

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(calculate_user_contribution(post_count=30, comment_count=40), 5)
        self.assertEqual(tier_info["contribution"], 5)

    def test_activity_contribution_is_calculated_per_day(self):
        first_day = timezone.now() - timezone.timedelta(days=1)
        second_day = timezone.now()
        first_post = self.create_post(created_at=first_day)
        second_post = self.create_post(created_at=second_day)

        for index in range(4):
            self.create_post(created_at=first_day)
        for index in range(9):
            self.create_comment(first_post, created_at=first_day)
        for index in range(4):
            self.create_post(created_at=second_day)
        for index in range(9):
            self.create_comment(second_post, created_at=second_day)

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 4)

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

    def test_approved_wrong_info_and_edit_place_reports_grant_five_points(self):
        PlaceReport.objects.create(
            user=self.user,
            report_type="wrong_info",
            status="approved",
            description="오류 제보",
        )
        PlaceReport.objects.create(
            user=self.user,
            report_type="edit_place",
            status="approved",
            description="장소 수정 제보",
        )

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 10)

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

    @skip(
        "Spring 으로 이관됨. 대체 테스트: spring-api AuthApiTest.meIncludesContributionAndTier, "
        "signupResponseIncludesTier"
    )
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
        self.assertEqual(user_data["tier"], "iron")
        self.assertEqual(user_data["nickname_color"], TIER_COLORS["iron"])

    def test_tier_is_calculated_from_contribution(self):
        for index in range(50):
            PlaceReport.objects.create(
                user=self.user,
                report_type="new_place",
                status="approved",
                description=f"새 장소 제보 {index}",
            )

        tier_info = get_user_tier_info(self.user)

        self.assertEqual(tier_info["contribution"], 1000)
        self.assertEqual(tier_info["tier"], "challenger")
        self.assertEqual(tier_info["tier_label"], "챌린저")
