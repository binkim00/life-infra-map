from django.contrib.auth.models import User
from django.test import TestCase
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
import os
import tempfile
from rest_framework.test import APIClient

from accounts.models import UserProfile
from boards.models import Comment, Inquiry, Post


class AccountDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="leaving", password="test-password")
        UserProfile.objects.create(user=self.user, nickname="기존 이름")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_deletes_account_and_private_data_but_anonymizes_public_content(self):
        post = Post.objects.create(author=self.user, title="제목", content="본문")
        comment = Comment.objects.create(author=self.user, post=post, content="댓글")
        inquiry = Inquiry.objects.create(author=self.user, title="문의", content="비공개 내용")

        response = self.client.post("/api/account-deletion/", {
            "username": "leaving", "confirmation": "계정 삭제",
        }, format="json")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        post.refresh_from_db()
        comment.refresh_from_db()
        self.assertEqual(post.author_id, comment.author_id)
        self.assertEqual(post.author.profile.nickname, "탈퇴한 사용자 (시스템)")
        self.assertFalse(post.author.is_active)
        self.assertFalse(post.author.has_usable_password())
        self.assertFalse(Inquiry.objects.filter(pk=inquiry.pk).exists())

    def test_requires_exact_confirmation(self):
        response = self.client.post("/api/account-deletion/", {
            "username": "someone-else", "confirmation": "계정 삭제",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_blocks_staff_account(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.post("/api/account-deletion/", {
            "username": "leaving", "confirmation": "계정 삭제",
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_removes_public_post_attachment_after_commit(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            post = Post.objects.create(
                author=self.user, title="제목", content="본문",
                image=SimpleUploadedFile("photo.jpg", b"test-image", content_type="image/jpeg"),
            )
            image_path = post.image.path
            self.assertTrue(os.path.exists(image_path))
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post("/api/account-deletion/", {
                    "username": "leaving", "confirmation": "계정 삭제",
                }, format="json")
            self.assertEqual(response.status_code, 204)
            self.assertFalse(os.path.exists(image_path))
