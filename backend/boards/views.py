from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

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
from .serializers import (
    AdminUserSerializer,
    CommentSerializer,
    InquiryAdminUpdateSerializer,
    InquirySerializer,
    NotificationSerializer,
    PostDetailSerializer,
    PostListSerializer,
    ReportCreateSerializer,
    ReportListSerializer,
    UserPenaltySerializer,
)


ADMIN_ONLY_MESSAGE = "관리자만 접근할 수 있습니다."


def admin_only_response():
    return Response(
        {"detail": ADMIN_ONLY_MESSAGE},
        status=status.HTTP_403_FORBIDDEN,
    )


def get_current_penalty(user):
    if not user or not user.is_authenticated:
        return None

    for penalty in user.penalties.order_by("-created_at"):
        if penalty.is_current:
            return penalty

    return None


def serialize_penalty(penalty):
    if not penalty:
        return {
            "is_suspended": False,
            "suspended_until": None,
            "is_permanent_ban": False,
            "reason": "",
            "penalty_type": "",
        }

    return {
        "is_suspended": True,
        "suspended_until": penalty.end_at,
        "is_permanent_ban": penalty.penalty_type == "permanent_ban",
        "reason": penalty.reason,
        "penalty_type": penalty.penalty_type,
    }


def blocked_response(user):
    penalty = get_current_penalty(user)

    if not penalty:
        return None

    return Response(
        {
            "detail": "현재 활동정지 또는 밴 상태라 이 작업을 할 수 없습니다.",
            "penalty": serialize_penalty(penalty),
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def create_notification(recipient, title, message, notification_type="system", sender=None):
    return Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        title=title,
        message=message,
    )


def get_penalty_end_at(penalty_type):
    now = timezone.now()

    if penalty_type == "suspend_3_days":
        return now + timedelta(days=3)

    if penalty_type == "suspend_7_days":
        return now + timedelta(days=7)

    if penalty_type == "suspend_30_days":
        return now + timedelta(days=30)

    if penalty_type == "suspend_1_year":
        return now + timedelta(days=365)

    return None


def create_user_penalty(user, penalty_type, reason, created_by):
    if penalty_type == "warning":
        create_notification(
            recipient=user,
            sender=created_by,
            notification_type="admin_warning",
            title="관리자 경고 안내",
            message=reason,
        )
        return None

    UserPenalty.objects.filter(user=user, is_active=True).update(is_active=False)

    penalty = UserPenalty.objects.create(
        user=user,
        penalty_type=penalty_type,
        reason=reason,
        end_at=get_penalty_end_at(penalty_type),
        created_by=created_by,
    )

    create_notification(
        recipient=user,
        sender=created_by,
        notification_type="penalty_notice",
        title="계정 제재 안내",
        message=reason,
    )

    return penalty


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def post_list_create(request):
    if request.method == "GET":
        board_type = request.GET.get("board_type", "free")

        posts = Post.objects.filter(board_type=board_type)
        serializer = PostListSerializer(
            posts,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)

    if request.method == "POST":
        if not request.user.is_authenticated:
            return Response(
                {"detail": "로그인이 필요합니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        penalty_response = blocked_response(request.user)
        if penalty_response:
            return penalty_response

        board_type = request.data.get("board_type", "free")

        if board_type == "notice" and not request.user.is_staff:
            return Response(
                {"detail": "공지사항은 관리자만 작성할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PostDetailSerializer(data=request.data)

        if serializer.is_valid():
            post = serializer.save(author=request.user)
            result_serializer = PostDetailSerializer(
                post,
                context={"request": request},
            )

            return Response(result_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def post_detail_update_delete(request, post_id):
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return Response(
            {"detail": "게시글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        post.view_count += 1
        post.save(update_fields=["view_count"])

        serializer = PostDetailSerializer(
            post,
            context={"request": request},
        )

        return Response(serializer.data)

    if not request.user.is_authenticated:
        return Response(
            {"detail": "로그인이 필요합니다."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if post.board_type == "notice":
        if not request.user.is_staff:
            return Response(
                {"detail": "공지사항은 관리자만 수정/삭제할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        if post.author != request.user and not request.user.is_staff:
            return Response(
                {"detail": "작성자만 수정/삭제할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

    if request.method in ["PUT", "PATCH"]:
        serializer = PostDetailSerializer(
            post,
            data=request.data,
            partial=request.method == "PATCH",
        )

        if serializer.is_valid():
            updated_post = serializer.save()
            result_serializer = PostDetailSerializer(
                updated_post,
                context={"request": request},
            )

            return Response(result_serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        post.delete()

        return Response(
            {"message": "게시글이 삭제되었습니다."},
            status=status.HTTP_204_NO_CONTENT,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def comment_create(request, post_id):
    penalty_response = blocked_response(request.user)
    if penalty_response:
        return penalty_response

    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return Response(
            {"detail": "게시글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = CommentSerializer(data=request.data)

    if serializer.is_valid():
        comment = serializer.save(
            post=post,
            author=request.user,
        )

        result_serializer = CommentSerializer(
            comment,
            context={"request": request},
        )

        return Response(result_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def comment_update_delete(request, comment_id):
    try:
        comment = Comment.objects.get(id=comment_id)
    except Comment.DoesNotExist:
        return Response(
            {"detail": "댓글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if comment.author != request.user and not request.user.is_staff:
        return Response(
            {"detail": "댓글 작성자만 수정/삭제할 수 있습니다."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method in ["PUT", "PATCH"]:
        serializer = CommentSerializer(
            comment,
            data=request.data,
            partial=request.method == "PATCH",
        )

        if serializer.is_valid():
            updated_comment = serializer.save()
            result_serializer = CommentSerializer(
                updated_comment,
                context={"request": request},
            )

            return Response(result_serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        comment.delete()

        return Response(
            {"message": "댓글이 삭제되었습니다."},
            status=status.HTTP_204_NO_CONTENT,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_post_like(request, post_id):
    penalty_response = blocked_response(request.user)
    if penalty_response:
        return penalty_response

    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return Response(
            {"detail": "게시글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    like, created = PostLike.objects.get_or_create(
        post=post,
        user=request.user,
    )

    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    return Response({
        "liked": liked,
        "likes_count": post.post_likes.count(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_comment_like(request, comment_id):
    penalty_response = blocked_response(request.user)
    if penalty_response:
        return penalty_response

    try:
        comment = Comment.objects.get(id=comment_id)
    except Comment.DoesNotExist:
        return Response(
            {"detail": "댓글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    like, created = CommentLike.objects.get_or_create(
        comment=comment,
        user=request.user,
    )

    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    return Response({
        "liked": liked,
        "likes_count": comment.comment_likes.count(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_post(request, post_id):
    penalty_response = blocked_response(request.user)
    if penalty_response:
        return penalty_response

    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return Response(
            {"detail": "게시글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if post.board_type != "free":
        return Response(
            {"detail": "자유게시판 글만 신고할 수 있습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ReportCreateSerializer(data=request.data)

    if serializer.is_valid():
        report = serializer.save(
            reporter=request.user,
            post=post,
        )

        return Response(
            ReportListSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_comment(request, comment_id):
    penalty_response = blocked_response(request.user)
    if penalty_response:
        return penalty_response

    try:
        comment = Comment.objects.select_related("post").get(id=comment_id)
    except Comment.DoesNotExist:
        return Response(
            {"detail": "댓글을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if comment.post.board_type != "free":
        return Response(
            {"detail": "자유게시판 댓글만 신고할 수 있습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ReportCreateSerializer(data=request.data)

    if serializer.is_valid():
        report = serializer.save(
            reporter=request.user,
            comment=comment,
        )

        return Response(
            ReportListSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_list(request):
    if not request.user.is_staff:
        return admin_only_response()

    report_status = request.GET.get("status", "pending")

    reports = Report.objects.select_related(
        "reporter",
        "post",
        "post__author",
        "comment",
        "comment__author",
        "comment__post",
    )

    if report_status != "all":
        reports = reports.filter(status=report_status)

    serializer = ReportListSerializer(reports, many=True)

    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def process_report(request, report_id):
    if not request.user.is_staff:
        return admin_only_response()

    try:
        report = Report.objects.select_related(
            "reporter",
            "post",
            "post__author",
            "comment",
            "comment__author",
            "comment__post",
        ).get(id=report_id)
    except Report.DoesNotExist:
        return Response(
            {"detail": "신고 내역을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    action = request.data.get("action")
    admin_memo = request.data.get("admin_memo", "").strip()

    if action not in ["passed", "penalized"]:
        return Response(
            {"detail": "처리 방식이 올바르지 않습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report.status = action
    report.admin_memo = admin_memo
    report.processed_by = request.user
    report.processed_at = timezone.now()
    reported_user = report.reported_user

    if action == "passed":
        create_notification(
            recipient=report.reporter,
            sender=request.user,
            notification_type="report_passed",
            title="신고 검토 결과 안내",
            message="신고가 검토되었으나 조치 없이 종료되었습니다.",
        )
    else:
        penalty_type = request.data.get("penalty_type", "warning")
        penalty_reason = request.data.get("penalty_reason", admin_memo or report.reason).strip()

        if reported_user:
            create_user_penalty(
                user=reported_user,
                penalty_type=penalty_type,
                reason=penalty_reason or "신고 처리에 따른 관리자 조치입니다.",
                created_by=request.user,
            )

        report.save()

        if report.post_id:
            report.post.delete()
        elif report.comment_id:
            report.comment.delete()

        create_notification(
            recipient=report.reporter,
            sender=request.user,
            notification_type="report_penalty",
            title="신고 처리 완료 안내",
            message="신고해주신 내용이 확인되어 조치되었습니다.",
        )

    if action == "passed":
        report.save()

    serializer = ReportListSerializer(report)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request):
    Notification.objects.filter(
        recipient=request.user,
        created_at__lt=timezone.now() - timedelta(days=3),
    ).delete()
    notifications = Notification.objects.filter(recipient=request.user)
    serializer = NotificationSerializer(notifications, many=True)
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_read(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, recipient=request.user)
    except Notification.DoesNotExist:
        return Response(
            {"detail": "알림을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return Response(NotificationSerializer(notification).data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def notification_read_all(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return Response({"message": "모든 알림을 읽음 처리했습니다."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def inquiry_create(request):
    penalty_response = blocked_response(request.user)
    if penalty_response:
        return penalty_response

    serializer = InquirySerializer(data=request.data)

    if serializer.is_valid():
        inquiry = serializer.save(author=request.user)
        return Response(InquirySerializer(inquiry).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_inquiry_list(request):
    serializer = InquirySerializer(
        Inquiry.objects.filter(author=request.user),
        many=True,
    )
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def inquiry_detail(request, inquiry_id):
    try:
        inquiry = Inquiry.objects.get(id=inquiry_id)
    except Inquiry.DoesNotExist:
        return Response(
            {"detail": "문의를 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if inquiry.author != request.user and not request.user.is_staff:
        return Response(
            {"detail": "본인이 작성한 문의만 확인할 수 있습니다."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(InquirySerializer(inquiry).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_inquiry_list(request):
    if not request.user.is_staff:
        return admin_only_response()

    serializer = InquirySerializer(Inquiry.objects.all(), many=True)
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def admin_inquiry_update(request, inquiry_id):
    if not request.user.is_staff:
        return admin_only_response()

    try:
        inquiry = Inquiry.objects.get(id=inquiry_id)
    except Inquiry.DoesNotExist:
        return Response(
            {"detail": "문의를 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = InquiryAdminUpdateSerializer(inquiry, data=request.data, partial=True)

    if serializer.is_valid():
        updated = serializer.save()

        if updated.status == "answered" and updated.admin_reply:
            updated.replied_by = request.user
            updated.replied_at = timezone.now()
            updated.save(update_fields=["replied_by", "replied_at", "updated_at"])
            create_notification(
                recipient=updated.author,
                sender=request.user,
                notification_type="inquiry_answered",
                title="문의 답변이 등록되었습니다.",
                message=updated.admin_reply,
            )

        return Response(InquirySerializer(updated).data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_user_list(request):
    if not request.user.is_staff:
        return admin_only_response()

    users = User.objects.annotate(
        posts_count=Count("posts", distinct=True),
        comments_count=Count("comments", distinct=True),
        received_reports_count=(
            Count("posts__reports", distinct=True)
            + Count("comments__reports", distinct=True)
        ),
    ).order_by("-received_reports_count", "id")

    serializer = AdminUserSerializer(users, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_user_detail(request, user_id):
    if not request.user.is_staff:
        return admin_only_response()

    try:
        user = User.objects.annotate(
            posts_count=Count("posts", distinct=True),
            comments_count=Count("comments", distinct=True),
            received_reports_count=(
                Count("posts__reports", distinct=True)
                + Count("comments__reports", distinct=True)
            ),
        ).get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "사용자를 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "user": AdminUserSerializer(user).data,
        "posts": PostListSerializer(
            Post.objects.filter(author=user),
            many=True,
            context={"request": request},
        ).data,
        "comments": CommentSerializer(
            Comment.objects.filter(author=user).select_related("post"),
            many=True,
            context={"request": request},
        ).data,
        "penalties": UserPenaltySerializer(
            UserPenalty.objects.filter(user=user),
            many=True,
        ).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_create_user_penalty(request, user_id):
    if not request.user.is_staff:
        return admin_only_response()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "사용자를 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    penalty_type = request.data.get("penalty_type")
    reason = request.data.get("reason", "").strip()

    if penalty_type not in dict(UserPenalty.PENALTY_TYPE_CHOICES):
        return Response(
            {"detail": "제재 종류가 올바르지 않습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not reason:
        return Response(
            {"detail": "제재 사유를 입력해주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    penalty = create_user_penalty(
        user=user,
        penalty_type=penalty_type,
        reason=reason,
        created_by=request.user,
    )

    if penalty is None:
        return Response({"message": "경고 알림을 전송했습니다."}, status=status.HTTP_201_CREATED)

    return Response(UserPenaltySerializer(penalty).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_create_user_notification(request, user_id):
    if not request.user.is_staff:
        return admin_only_response()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "사용자를 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    title = request.data.get("title", "").strip()
    message = request.data.get("message", "").strip()

    if not title or not message:
        return Response(
            {"detail": "제목과 메시지를 입력해주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    notification = create_notification(
        recipient=user,
        sender=request.user,
        notification_type="admin_warning",
        title=title,
        message=message,
    )

    return Response(NotificationSerializer(notification).data, status=status.HTTP_201_CREATED)
