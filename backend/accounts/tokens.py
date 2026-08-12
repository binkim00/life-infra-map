"""
Spring 과 같은 형식의 액세스 토큰을 Django 에서도 발급합니다.

회원가입은 프로필 사진 업로드(multipart) 때문에 아직 Django 가 처리합니다.
그런데 로그인은 Spring 이 담당하므로, 두 경로가 서로 다른 자격증명을 주면
프론트가 저장한 값이 어느 쪽인지에 따라 인증이 깨집니다.

그래서 어느 쪽으로 가입/로그인하든 같은 JWT 를 돌려줍니다.
클레임은 `spring-api` 의 `JwtService` 와 맞춰야 합니다.
"""

from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings


def issue_access_token(user):
    """사용자에게 줄 액세스 토큰을 만든다. 비밀키가 없으면 빈 문자열을 돌려준다."""
    secret = getattr(settings, "JWT_SECRET", "")
    if not secret or not user:
        return ""

    now = datetime.now(timezone.utc)
    minutes = int(getattr(settings, "JWT_ACCESS_MINUTES", 120))

    return jwt.encode(
        {
            "sub": str(user.pk),
            "username": user.get_username(),
            "iat": now,
            "exp": now + timedelta(minutes=minutes),
        },
        secret,
        algorithm=getattr(settings, "JWT_ALGORITHM", "HS256"),
    )


def access_token_seconds():
    return int(getattr(settings, "JWT_ACCESS_MINUTES", 120)) * 60
