from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .serializers import LoginSerializer, SignupSerializer, UserSerializer


@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request):
    serializer = SignupSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    token, _ = Token.objects.get_or_create(user=user)

    return Response(
        {
            "message": "회원가입이 완료되었습니다.",
            "token": token.key,
            "user": UserSerializer(user).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.validated_data["user"]

    from boards.views import get_current_penalty, serialize_penalty

    current_penalty = get_current_penalty(user)

    if current_penalty:
        penalty_data = serialize_penalty(current_penalty)
        penalty_data.update({
            "end_at": current_penalty.end_at,
            "message": current_penalty.reason,
        })

        return Response(
            {
                "detail": "현재 활동정지 또는 밴 상태라 로그인할 수 없습니다.",
                "penalty": penalty_data,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    token, _ = Token.objects.get_or_create(user=user)

    return Response({
        "message": "로그인되었습니다.",
        "token": token.key,
        "user": UserSerializer(user).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    try:
        request.user.auth_token.delete()
    except Token.DoesNotExist:
        pass

    return Response({
        "message": "로그아웃되었습니다."
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({
        "user": UserSerializer(request.user).data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mypage(request):
    from boards.models import Comment, Inquiry, Notification, Post, PostLike
    from boards.serializers import (
        CommentSerializer,
        InquirySerializer,
        NotificationSerializer,
        PostListSerializer,
    )
    from boards.views import get_current_penalty, serialize_penalty

    current_penalty = get_current_penalty(request.user)

    return Response({
        "user": UserSerializer(request.user).data,
        "posts": PostListSerializer(
            Post.objects.filter(author=request.user),
            many=True,
            context={"request": request},
        ).data,
        "comments": CommentSerializer(
            Comment.objects.filter(author=request.user).select_related("post"),
            many=True,
            context={"request": request},
        ).data,
        "liked_posts": PostListSerializer(
            Post.objects.filter(post_likes__user=request.user),
            many=True,
            context={"request": request},
        ).data,
        "notifications": NotificationSerializer(
            Notification.objects.filter(recipient=request.user),
            many=True,
        ).data,
        "inquiries": InquirySerializer(
            Inquiry.objects.filter(author=request.user),
            many=True,
        ).data,
        "penalty": serialize_penalty(current_penalty),
    })
