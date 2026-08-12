from unittest import skip
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Notification, Post


class ReportNotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="staff",
            password="password",
            is_staff=True,
        )
        self.reporter = User.objects.create_user(
            username="reporter",
            password="password",
        )
        self.author = User.objects.create_user(
            username="author",
            password="password",
        )
        self.post = Post.objects.create(
            author=self.author,
            board_type="free",
            title="신고 대상 게시글",
            content="신고 대상 내용입니다.",
        )

    @skip("Spring 으로 이관됨. 대체 테스트: spring-api ReportApiTest.reportNotifiesStaff")
    def test_report_post_notifies_staff_users(self):
        self.client.force_authenticate(user=self.reporter)

        response = self.client.post(
            f"/api/boards/posts/{self.post.id}/report/",
            {
                "reason": "부적절한 내용입니다.",
            },
        )

        self.assertEqual(response.status_code, 201)
        notification = Notification.objects.get(
            recipient=self.staff_user,
            notification_type="report_received",
        )
        self.assertEqual(notification.sender, self.reporter)
        self.assertEqual(notification.target_post, self.post)
        self.assertIn("새 신고가 접수되었습니다.", notification.title)
