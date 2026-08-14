"""
Django 는 검색과 검색 데이터를 직접 변경하는 기능만 담당합니다.

계정·게시판·알림·문의·관리자 API는 Spring(`spring-api`)으로 이관했고,
프론트는 `src/api/serviceRoutes.js`에서 경로별로 담당 서비스에 보냅니다.
계정·게시판 앱의 모델과 마이그레이션은 두 서비스가 공유하는 PostgreSQL 스키마를
관리하고 검색 서비스가 사용자 활동을 읽는 데 필요하므로 계속 유지합니다.
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
