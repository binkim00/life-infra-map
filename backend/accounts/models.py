from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="사용자",
    )
    nickname = models.CharField(max_length=50, unique=True, verbose_name="닉네임")
    profile_image = models.FileField(
        upload_to="profile_images/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "gif", "webp"]),
        ],
        verbose_name="프로필 사진",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        verbose_name = "사용자 프로필"
        verbose_name_plural = "사용자 프로필"

    def __str__(self):
        return f"{self.user.username} ({self.nickname})"
