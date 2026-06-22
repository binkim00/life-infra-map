from django.contrib import admin
from .models import (
    Comment,
    CommentLike,
    Inquiry,
    Notification,
    Post,
    PostLike,
    Report,
    UserPenalty,
)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "board_type", "title", "author", "is_pinned", "created_at"]
    list_filter = ["board_type", "is_pinned", "created_at"]
    search_fields = ["title", "content", "author__username"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "author", "created_at"]
    search_fields = ["content", "author__username", "post__title"]


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "user", "created_at"]


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ["id", "comment", "user", "created_at"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "target_type", "reporter", "target_title", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = [
        "reason",
        "reporter__username",
        "post__title",
        "comment__content",
    ]

    def target_type(self, obj):
        return "게시글" if obj.post_id else "댓글"

    target_type.short_description = "신고 대상"

    def target_title(self, obj):
        if obj.post_id:
            return obj.post.title

        return obj.comment.post.title

    target_title.short_description = "대상 글"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "recipient", "notification_type", "title", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read", "created_at"]
    search_fields = ["title", "message", "recipient__username"]


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "author", "status", "replied_by", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["title", "content", "author__username", "admin_reply"]


@admin.register(UserPenalty)
class UserPenaltyAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "penalty_type", "is_active", "end_at", "created_by", "created_at"]
    list_filter = ["penalty_type", "is_active", "created_at"]
    search_fields = ["user__username", "reason", "created_by__username"]
