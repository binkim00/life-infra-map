"""
Spring 서비스가 발급한 액세스 토큰을 Django 에서도 검증합니다.

인증은 Spring 이 담당하고 recommendations(AI 검색)는 Django 에 남기기로 했으므로,
두 서비스가 같은 토큰을 이해해야 합니다.

토큰 형식은 `spring-api` 의 `JwtService` 와 맞춰야 합니다.
클레임을 바꾸면 양쪽을 함께 고쳐야 합니다.

    sub       사용자 id (문자열)
    username  로그인 아이디
    exp/iat   만료/발급 시각

기존 DRF `TokenAuthentication` 도 그대로 둡니다.
아직 Django 로그인을 쓰는 화면이 있어서, 이관이 끝날 때까지 둘 다 받습니다.
"""

import logging

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions


logger = logging.getLogger(__name__)

AUTH_HEADER_PREFIX = "bearer"


class SharedJWTAuthentication(authentication.BaseAuthentication):
    """`Authorization: Bearer <token>` 를 Spring 과 같은 비밀키로 검증한다."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower().decode("utf-8", "ignore") != AUTH_HEADER_PREFIX:
            # Bearer 가 아니면 다른 인증 방식이 처리하도록 넘긴다.
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Authorization 헤더 형식이 올바르지 않습니다.")

        secret = getattr(settings, "JWT_SECRET", "")
        if not secret:
            logger.warning("JWT_SECRET 이 비어 있어 Bearer 토큰을 검증할 수 없습니다.")
            raise exceptions.AuthenticationFailed("토큰 검증 설정이 준비되지 않았습니다.")

        # JJWT 0.12 는 알고리즘을 지정하지 않으면 키 길이에 따라 HS512 를
        # 선택합니다. Spring 이 HS256 을 명시하기 전 발급된 토큰도 만료될
        # 때까지 사용할 수 있도록 HS512 만 한시적으로 함께 허용합니다.
        configured_algorithm = getattr(settings, "JWT_ALGORITHM", "HS256")
        accepted_algorithms = list(dict.fromkeys((configured_algorithm, "HS512")))

        try:
            payload = jwt.decode(
                header[1].decode("utf-8", "ignore"),
                secret,
                algorithms=accepted_algorithms,
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("토큰이 올바르지 않습니다.")

        user_id = payload.get("sub")
        if not user_id:
            raise exceptions.AuthenticationFailed("토큰에 사용자 정보가 없습니다.")

        user_model = get_user_model()
        try:
            user = user_model.objects.get(pk=int(user_id))
        except (ValueError, user_model.DoesNotExist):
            raise exceptions.AuthenticationFailed("토큰의 사용자를 찾을 수 없습니다.")

        if not user.is_active:
            raise exceptions.AuthenticationFailed("비활성화된 계정입니다.")

        return (user, payload)

    def authenticate_header(self, request):
        # 401 응답에 WWW-Authenticate 를 붙여 준다. 없으면 DRF 가 403 으로 내려간다.
        return "Bearer"
