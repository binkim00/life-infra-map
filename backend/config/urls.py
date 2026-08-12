"""
Django 는 검색만 담당합니다.

계정·게시판·알림·문의·관리자는 Spring(`spring-api`)으로 이관했고,
프론트는 `src/api/serviceRoutes.js`에서 경로별로 담당 서비스에 보냅니다.

이관된 뷰 코드(`accounts/views.py`, `boards/views.py`)는 아직 남겨 두었습니다.
Spring 컨트롤러 테스트가 붙기 전에 지우면 되돌릴 근거가 사라지기 때문입니다.
여기서 URL 등록만 내려 두면 외부에서 닿지 않으므로, 되돌릴 때는 이 파일만 고치면 됩니다.

삭제 시점: Spring 컨트롤러 테스트가 붙은 뒤
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/recommendations/", include("recommendations.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
