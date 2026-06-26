from datetime import timedelta

from django.contrib.auth.models import User
from rest_framework import serializers
from accounts.serializers import get_or_create_profile
from accounts.utils import get_user_tier_info
from .models import Comment, Inquiry, Notification, Post, Report, UserPenalty


def is_edited(obj):
    if not obj.created_at or not obj.updated_at:
        return False

    return obj.updated_at > obj.created_at + timedelta(seconds=1)


def get_file_url(serializer, file_field):
    if not file_field:
        return ""

    request = serializer.context.get("request")
    url = file_field.url

    if request:
        return request.build_absolute_uri(url)

    return url


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    author_nickname = serializers.SerializerMethodField()
    author_profile_image_url = serializers.SerializerMethodField()
    author_tier = serializers.SerializerMethodField()
    author_tier_label = serializers.SerializerMethodField()
    author_nickname_color = serializers.SerializerMethodField()
    post_title = serializers.CharField(source="post.title", read_only=True)
    post_board_type = serializers.CharField(source="post.board_type", read_only=True)
    likes_count = serializers.IntegerField(source="comment_likes.count", read_only=True)
    dislikes_count = serializers.IntegerField(source="comment_dislikes.count", read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_disliked = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "post_title",
            "post_board_type",
            "author",
            "parent",
            "author_username",
            "author_nickname",
            "author_profile_image_url",
            "author_tier",
            "author_tier_label",
            "author_nickname_color",
            "content",
            "likes_count",
            "dislikes_count",
            "is_liked",
            "is_disliked",
            "is_edited",
            "replies",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "post",
            "post_title",
            "post_board_type",
            "author",
            "parent",
            "author_username",
            "author_nickname",
            "author_profile_image_url",
            "author_tier",
            "author_tier_label",
            "author_nickname_color",
            "likes_count",
            "dislikes_count",
            "is_liked",
            "is_disliked",
            "is_edited",
            "replies",
            "created_at",
            "updated_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.comment_likes.filter(user=request.user).exists()

    def get_is_disliked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.comment_dislikes.filter(user=request.user).exists()

    def get_is_edited(self, obj):
        return is_edited(obj)

    def get_author_nickname(self, obj):
        return get_or_create_profile(obj.author).nickname

    def get_author_profile_image_url(self, obj):
        profile = get_or_create_profile(obj.author)
        return get_file_url(self, profile.profile_image)

    def get_author_tier(self, obj):
        return get_user_tier_info(obj.author)["tier"]

    def get_author_tier_label(self, obj):
        return get_user_tier_info(obj.author)["tier_label"]

    def get_author_nickname_color(self, obj):
        return get_user_tier_info(obj.author)["nickname_color"]

    def get_replies(self, obj):
        if obj.parent_id:
            return []

        serializer = CommentSerializer(
            obj.replies.all(),
            many=True,
            context=self.context,
        )
        return serializer.data


class PostListSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    author_nickname = serializers.SerializerMethodField()
    author_profile_image_url = serializers.SerializerMethodField()
    author_tier = serializers.SerializerMethodField()
    author_tier_label = serializers.SerializerMethodField()
    author_nickname_color = serializers.SerializerMethodField()
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)
    likes_count = serializers.IntegerField(source="post_likes.count", read_only=True)
    is_liked = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "author",
            "author_username",
            "author_nickname",
            "author_profile_image_url",
            "author_tier",
            "author_tier_label",
            "author_nickname_color",
            "board_type",
            "title",
            "image",
            "image_url",
            "view_count",
            "is_pinned",
            "comments_count",
            "likes_count",
            "is_liked",
            "is_edited",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "author_username",
            "author_nickname",
            "author_profile_image_url",
            "author_tier",
            "author_tier_label",
            "author_nickname_color",
            "image_url",
            "view_count",
            "is_pinned",
            "comments_count",
            "likes_count",
            "is_liked",
            "is_edited",
            "created_at",
            "updated_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.post_likes.filter(user=request.user).exists()

    def get_image_url(self, obj):
        return get_file_url(self, obj.image)

    def get_is_edited(self, obj):
        return is_edited(obj)

    def get_author_nickname(self, obj):
        return get_or_create_profile(obj.author).nickname

    def get_author_profile_image_url(self, obj):
        profile = get_or_create_profile(obj.author)
        return get_file_url(self, profile.profile_image)

    def get_author_tier(self, obj):
        return get_user_tier_info(obj.author)["tier"]

    def get_author_tier_label(self, obj):
        return get_user_tier_info(obj.author)["tier_label"]

    def get_author_nickname_color(self, obj):
        return get_user_tier_info(obj.author)["nickname_color"]


class PostDetailSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    author_nickname = serializers.SerializerMethodField()
    author_profile_image_url = serializers.SerializerMethodField()
    author_tier = serializers.SerializerMethodField()
    author_tier_label = serializers.SerializerMethodField()
    author_nickname_color = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)
    likes_count = serializers.IntegerField(source="post_likes.count", read_only=True)
    is_liked = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "author",
            "author_username",
            "author_nickname",
            "author_profile_image_url",
            "author_tier",
            "author_tier_label",
            "author_nickname_color",
            "board_type",
            "title",
            "content",
            "image",
            "image_url",
            "view_count",
            "is_pinned",
            "comments",
            "comments_count",
            "likes_count",
            "is_liked",
            "is_edited",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "author",
            "author_username",
            "author_nickname",
            "author_profile_image_url",
            "author_tier",
            "author_tier_label",
            "author_nickname_color",
            "image_url",
            "view_count",
            "is_pinned",
            "comments",
            "comments_count",
            "likes_count",
            "is_liked",
            "is_edited",
            "created_at",
            "updated_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.post_likes.filter(user=request.user).exists()

    def get_image_url(self, obj):
        return get_file_url(self, obj.image)

    def get_is_edited(self, obj):
        return is_edited(obj)

    def get_author_nickname(self, obj):
        return get_or_create_profile(obj.author).nickname

    def get_author_profile_image_url(self, obj):
        profile = get_or_create_profile(obj.author)
        return get_file_url(self, profile.profile_image)

    def get_author_tier(self, obj):
        return get_user_tier_info(obj.author)["tier"]

    def get_author_tier_label(self, obj):
        return get_user_tier_info(obj.author)["tier_label"]

    def get_author_nickname_color(self, obj):
        return get_user_tier_info(obj.author)["nickname_color"]

    def get_comments(self, obj):
        comments = obj.comments.filter(parent__isnull=True).prefetch_related("replies")
        serializer = CommentSerializer(comments, many=True, context=self.context)
        return serializer.data


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
    target_route = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "sender",
            "sender_username",
            "notification_type",
            "target_post",
            "target_comment",
            "target_route",
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
            "target_post",
            "target_comment",
            "target_route",
            "is_read",
            "created_at",
        ]

    def get_target_route(self, obj):
        if obj.notification_type == "report_received":
            return "/admin/reports"

        if obj.notification_type == "inquiry_answered":
            return "/inquiries/my"

        post = obj.target_post

        if not post and obj.target_comment:
            post = obj.target_comment.post

        if not post:
            return ""

        route = f"/boards/{post.board_type}/{post.id}"

        if obj.target_comment_id:
            return f"{route}#comment-{obj.target_comment_id}"

        return route


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


class InquiryHistorySerializer(serializers.ModelSerializer):
    replied_by_username = serializers.CharField(source="replied_by.username", read_only=True)

    class Meta:
        model = Inquiry
        fields = [
            "id",
            "title",
            "content",
            "status",
            "admin_reply",
            "replied_by_username",
            "replied_at",
            "created_at",
        ]


class AdminInquirySerializer(InquirySerializer):
    previous_inquiries = serializers.SerializerMethodField()
    previous_inquiries_count = serializers.SerializerMethodField()

    class Meta(InquirySerializer.Meta):
        fields = InquirySerializer.Meta.fields + [
            "previous_inquiries",
            "previous_inquiries_count",
        ]
        read_only_fields = InquirySerializer.Meta.read_only_fields + [
            "previous_inquiries",
            "previous_inquiries_count",
        ]

    def get_previous_queryset(self, obj):
        return Inquiry.objects.filter(author=obj.author).exclude(id=obj.id).order_by("-created_at")

    def get_previous_inquiries(self, obj):
        return InquiryHistorySerializer(self.get_previous_queryset(obj), many=True).data

    def get_previous_inquiries_count(self, obj):
        return self.get_previous_queryset(obj).count()


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
