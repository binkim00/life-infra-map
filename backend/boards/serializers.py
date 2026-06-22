from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Comment, Inquiry, Notification, Post, Report, UserPenalty


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    likes_count = serializers.IntegerField(source="comment_likes.count", read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "author",
            "author_username",
            "content",
            "likes_count",
            "is_liked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "post",
            "author",
            "author_username",
            "likes_count",
            "is_liked",
            "created_at",
            "updated_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.comment_likes.filter(user=request.user).exists()


class PostListSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)
    likes_count = serializers.IntegerField(source="post_likes.count", read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "author",
            "author_username",
            "board_type",
            "title",
            "view_count",
            "is_pinned",
            "comments_count",
            "likes_count",
            "is_liked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "author_username",
            "view_count",
            "is_pinned",
            "comments_count",
            "likes_count",
            "is_liked",
            "created_at",
            "updated_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.post_likes.filter(user=request.user).exists()


class PostDetailSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)
    likes_count = serializers.IntegerField(source="post_likes.count", read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "author",
            "author_username",
            "board_type",
            "title",
            "content",
            "view_count",
            "is_pinned",
            "comments",
            "comments_count",
            "likes_count",
            "is_liked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "author_username",
            "view_count",
            "is_pinned",
            "comments",
            "comments_count",
            "likes_count",
            "is_liked",
            "created_at",
            "updated_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.post_likes.filter(user=request.user).exists()


class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id",
            "reason",
        ]
        read_only_fields = [
            "id",
        ]

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("신고 사유를 입력해주세요.")

        if len(value.strip()) < 5:
            raise serializers.ValidationError("신고 사유는 5자 이상 입력해주세요.")

        return value.strip()


class ReportListSerializer(serializers.ModelSerializer):
    reporter_username = serializers.CharField(source="reporter.username", read_only=True)
    reported_user_id = serializers.SerializerMethodField()
    reported_username = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    target_content = serializers.SerializerMethodField()
    post_id = serializers.SerializerMethodField()
    post_title = serializers.SerializerMethodField()
    processed_by_username = serializers.CharField(source="processed_by.username", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "reporter",
            "reporter_username",
            "reported_user_id",
            "reported_username",
            "target_type",
            "target_id",
            "target_content",
            "post_id",
            "post_title",
            "reason",
            "status",
            "admin_memo",
            "processed_by",
            "processed_by_username",
            "processed_at",
            "created_at",
        ]

    def get_reported_user_id(self, obj):
        user = obj.reported_user
        return user.id if user else None

    def get_reported_username(self, obj):
        user = obj.reported_user
        return user.username if user else ""

    def get_target_type(self, obj):
        if not obj.post_id and not obj.comment_id:
            return "deleted"

        return "post" if obj.post_id else "comment"

    def get_target_id(self, obj):
        return obj.post_id or obj.comment_id

    def get_target_content(self, obj):
        if obj.post_id:
            return obj.post.content

        if not obj.comment_id:
            return "처리 과정에서 대상이 삭제되었습니다."

        return obj.comment.content

    def get_post_id(self, obj):
        if obj.post_id:
            return obj.post_id

        if not obj.comment_id:
            return None

        return obj.comment.post_id

    def get_post_title(self, obj):
        if obj.post_id:
            return obj.post.title

        if not obj.comment_id:
            return "삭제된 대상"

        return obj.comment.post.title


class NotificationSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "sender",
            "sender_username",
            "notification_type",
            "title",
            "message",
            "is_read",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "recipient",
            "sender",
            "sender_username",
            "notification_type",
            "is_read",
            "created_at",
        ]


class InquirySerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    replied_by_username = serializers.CharField(source="replied_by.username", read_only=True)

    class Meta:
        model = Inquiry
        fields = [
            "id",
            "author",
            "author_username",
            "title",
            "content",
            "status",
            "admin_reply",
            "replied_by",
            "replied_by_username",
            "replied_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "author_username",
            "status",
            "admin_reply",
            "replied_by",
            "replied_by_username",
            "replied_at",
            "created_at",
            "updated_at",
        ]

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("문의 제목을 입력해주세요.")

        return value.strip()

    def validate_content(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("문의 내용은 5자 이상 입력해주세요.")

        return value.strip()


class InquiryAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inquiry
        fields = [
            "status",
            "admin_reply",
        ]

    def validate(self, attrs):
        status_value = attrs.get("status")
        admin_reply = attrs.get("admin_reply", "")

        if status_value == "answered" and not admin_reply.strip():
            raise serializers.ValidationError({
                "admin_reply": "답변 내용을 입력해주세요.",
            })

        return attrs


class UserPenaltySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = UserPenalty
        fields = [
            "id",
            "user",
            "username",
            "penalty_type",
            "reason",
            "start_at",
            "end_at",
            "is_active",
            "created_by",
            "created_by_username",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "start_at",
            "end_at",
            "is_active",
            "created_by",
            "created_by_username",
            "created_at",
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    posts_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    received_reports_count = serializers.IntegerField(read_only=True)
    current_penalty = serializers.SerializerMethodField()
    recent_penalty = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_staff",
            "date_joined",
            "posts_count",
            "comments_count",
            "received_reports_count",
            "current_penalty",
            "recent_penalty",
        ]

    def get_current_penalty(self, obj):
        penalty = get_current_penalty(obj)

        if not penalty:
            return None

        return UserPenaltySerializer(penalty).data

    def get_recent_penalty(self, obj):
        penalty = obj.penalties.order_by("-created_at").first()

        if not penalty:
            return None

        return UserPenaltySerializer(penalty).data


def get_current_penalty(user):
    for penalty in user.penalties.order_by("-created_at"):
        if penalty.is_current:
            return penalty

    return None
