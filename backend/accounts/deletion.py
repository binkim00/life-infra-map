"""Authenticated account deletion; Django owns the shared database schema."""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import UserProfile
from boards.models import Comment, Post
from recommendations.models import PlaceInteractionEvent, PlaceReportImage, PlaceTagEvidence


logger = logging.getLogger(__name__)
DELETED_USERNAME = "_deleted_account_system"
DELETED_NICKNAME = "탈퇴한 사용자 (시스템)"


def _deleted_author():
    user_model = get_user_model()
    author, created = user_model.objects.get_or_create(
        username=DELETED_USERNAME,
        defaults={"is_active": False, "email": ""},
    )
    if created:
        author.set_unusable_password()
        author.save(update_fields=["password"])
    if author.is_active or author.has_usable_password() or author.email:
        raise ValueError("Reserved deleted-account identity is unsafe")
    profile, _ = UserProfile.objects.get_or_create(user=author, defaults={"nickname": DELETED_NICKNAME})
    if profile.nickname != DELETED_NICKNAME:
        raise ValueError("Reserved deleted-account profile is unsafe")
    return author


def _delete_file(storage, name):
    try:
        storage.delete(name)
    except Exception:
        logger.exception("Account deletion left an uploaded file requiring cleanup")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def delete_my_account(request):
    user = request.user
    if user.is_staff or user.is_superuser:
        return Response({"detail": "관리자 계정은 이 경로에서 삭제할 수 없습니다."}, status=status.HTTP_403_FORBIDDEN)
    if request.data.get("username") != user.username or request.data.get("confirmation") != "계정 삭제":
        return Response({"detail": "아이디와 삭제 확인 문구를 입력해 주세요."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=user.pk)
        author = _deleted_author()
        files = []
        profile = UserProfile.objects.filter(user=user).first()
        if profile and profile.profile_image:
            files.append((profile.profile_image.storage, profile.profile_image.name))
        for post in Post.objects.filter(author=user).exclude(image="").iterator():
            if post.image:
                files.append((post.image.storage, post.image.name))
        for report_image in PlaceReportImage.objects.filter(report__user=user).iterator():
            if report_image.image:
                files.append((report_image.image.storage, report_image.image.name))
        Post.objects.filter(author=user).update(author=author, image=None)
        Comment.objects.filter(author=user).update(author=author)
        # These references use SET_NULL, which would otherwise retain user activity.
        PlaceTagEvidence.objects.filter(user=user).delete()
        PlaceInteractionEvent.objects.filter(user=user).delete()
        user.delete()
        transaction.on_commit(lambda: [_delete_file(storage, name) for storage, name in files])

    return Response(status=status.HTTP_204_NO_CONTENT)
