from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


class Post(models.Model):
    BOARD_TYPE_CHOICES = [
        ("free", "자유게시판"),
        ("notice", "공지사항"),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
        verbose_name="작성자",
    )

    board_type = models.CharField(
        max_length=20,
        choices=BOARD_TYPE_CHOICES,
        default="free",
        verbose_name="게시판 종류",
    )

    title = models.CharField(max_length=200, verbose_name="제목")
    content = models.TextField(verbose_name="내용")
    image = models.FileField(
        upload_to="board_images/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "gif", "webp"]),
        ],
        verbose_name="첨부 이미지",
    )

    view_count = models.PositiveIntegerField(default=0, verbose_name="조회수")
    is_pinned = models.BooleanField(default=False, verbose_name="상단 고정 여부")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"[{self.board_type}] {self.title}"


class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="게시글",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="작성자",
    )

    content = models.TextField(verbose_name="댓글 내용")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author} - {self.content[:20]}"


class PostLike(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="post_likes",
        verbose_name="게시글",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="post_likes",
        verbose_name="사용자",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="좋아요 날짜")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="unique_post_like",
            )
        ]

    def __str__(self):
        return f"{self.user} likes {self.post}"


class CommentLike(models.Model):
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="comment_likes",
        verbose_name="댓글",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comment_likes",
        verbose_name="사용자",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="좋아요 날짜")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "user"],
                name="unique_comment_like",
            )
        ]

    def __str__(self):
        return f"{self.user} likes comment {self.comment.id}"


class Report(models.Model):
    STATUS_CHOICES = [
        ("pending", "대기"),
        ("passed", "패스"),
        ("penalized", "패널티 조치"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name="신고자",
    )

    post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="reports",
        null=True,
        blank=True,
        verbose_name="신고 게시글",
    )

    comment = models.ForeignKey(
        Comment,
        on_delete=models.SET_NULL,
        related_name="reports",
        null=True,
        blank=True,
        verbose_name="신고 댓글",
    )

    reason = models.TextField(verbose_name="신고 사유")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="처리 상태",
    )
    admin_memo = models.TextField(blank=True, verbose_name="관리자 메모")
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="processed_reports",
        null=True,
        blank=True,
        verbose_name="처리 관리자",
    )
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="처리일")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="신고일")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(post__isnull=False, comment__isnull=True)
                    | models.Q(post__isnull=True, comment__isnull=False)
                    | models.Q(status="penalized", post__isnull=True, comment__isnull=True)
                ),
                name="report_has_exactly_one_target",
            )
        ]

    def __str__(self):
        target = self.post or self.comment
        return f"{self.reporter} reported {target}"

    @property
    def reported_user(self):
        if self.post_id:
            return self.post.author

        if self.comment_id:
            return self.comment.author

        return None


class Notification(models.Model):
    TYPE_CHOICES = [
        ("report_passed", "신고 패스"),
        ("report_penalty", "신고 조치"),
        ("admin_warning", "관리자 경고"),
        ("inquiry_answered", "문의 답변"),
        ("penalty_notice", "제재 안내"),
        ("system", "시스템"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="수신자",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="sent_notifications",
        null=True,
        blank=True,
        verbose_name="발신자",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default="system",
        verbose_name="알림 종류",
    )
    title = models.CharField(max_length=200, verbose_name="제목")
    message = models.TextField(verbose_name="내용")
    is_read = models.BooleanField(default=False, verbose_name="읽음 여부")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient} - {self.title}"


class Inquiry(models.Model):
    STATUS_CHOICES = [
        ("pending", "답변 대기"),
        ("answered", "답변 완료"),
        ("closed", "종료"),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inquiries",
        verbose_name="작성자",
    )
    title = models.CharField(max_length=200, verbose_name="제목")
    content = models.TextField(verbose_name="내용")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="상태",
    )
    admin_reply = models.TextField(blank=True, verbose_name="관리자 답변")
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="answered_inquiries",
        null=True,
        blank=True,
        verbose_name="답변 관리자",
    )
    replied_at = models.DateTimeField(null=True, blank=True, verbose_name="답변일")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class UserPenalty(models.Model):
    PENALTY_TYPE_CHOICES = [
        ("warning", "경고"),
        ("suspend_3_days", "3일 활동정지"),
        ("suspend_7_days", "7일 활동정지"),
        ("suspend_30_days", "30일 활동정지"),
        ("suspend_1_year", "1년 사용정지"),
        ("permanent_ban", "영구밴"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="penalties",
        verbose_name="제재 대상",
    )
    penalty_type = models.CharField(
        max_length=30,
        choices=PENALTY_TYPE_CHOICES,
        verbose_name="제재 종류",
    )
    reason = models.TextField(verbose_name="제재 사유")
    start_at = models.DateTimeField(default=timezone.now, verbose_name="시작일")
    end_at = models.DateTimeField(null=True, blank=True, verbose_name="종료일")
    is_active = models.BooleanField(default=True, verbose_name="활성 여부")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_penalties",
        null=True,
        blank=True,
        verbose_name="처리 관리자",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.penalty_type}"

    @property
    def is_current(self):
        if not self.is_active:
            return False

        if self.penalty_type == "permanent_ban":
            return True

        return self.end_at is not None and self.end_at > timezone.now()
