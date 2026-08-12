"""
Django 는 검색만 담당합니다.

계정·게시판·알림·문의·관리자는 Spring(`spring-api`)으로 이관했고,
프론트는 `src/api/serviceRoutes.js`에서 경로별로 담당 서비스에 보냅니다.

이관된 뷰 코드(`accounts/views.py`, `boards/views.py`)는 아직 남겨 두었습니다.
Spring 컨트롤러 테스트가 붙기 전에 지우면 되돌릴 근거가 사라지기 때문입니다.
여기서 URL 등록만 내려 두면 외부에서 닿지 않으므로, 되돌릴 때는 이 파일만 고치면 됩니다.

삭제 가능 여부 (spring-api 테스트 93개 기준)

    accounts/views.py   삭제 가능
        로그인·회원가입·내정보·비밀번호변경·닉네임·프로필사진·마이페이지·로그아웃이
        `AuthApiTest`(21개)로 덮였습니다.
    boards/views.py     삭제 가능
        글·댓글·반응·비로그인조회는 `BoardApiTest`(17개),
        신고는 `ReportApiTest`(12개),
        알림·문의는 `UserDataApiTest`(18개),
        관리자 권한 경계는 `AdminApiTest`(17개)로 덮였습니다.

예외가 하나 있습니다.
프로필 사진과 게시글 이미지의 multipart 업로드는 저장소(MinIO)가 필요해 테스트가 없습니다.
JSON 으로 키를 넘기는 경로만 확인했습니다. 업로드 동작을 바꿀 때는 수동으로 확인하세요.
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
