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