"""
검색과, 검색 데이터를 건드리는 기능만 남깁니다.

- 저장 장소(`saved-places`)는 저장 시점 정보를 복사해 둘 뿐 검색 데이터를 바꾸지 않아 Spring 으로 이관했습니다.
- 장소 제보(`place-reports`)는 **Django 에 남습니다.** 승인하면 `apply_place_report_approval()` 이
  `Place` 를 만들고 `PlaceTag` 를 붙입니다. 즉 승인이 검색 데이터를 직접 바꿉니다.
  장소/태그는 Django 소유이므로 이 쓰기를 Spring 으로 넘기면 경계가 무너집니다.
  Spring 은 기여도 계산을 위해 `placereport` 를 읽기만 합니다.
- 검색 개인화(`preferences`, `search-logs`)는 검색 로그에서 파생되고 검색에만 쓰이므로 여기 남습니다.

이관된 뷰 함수는 `views.py` 에 아직 남아 있습니다. Spring 컨트롤러 테스트가 붙은 뒤에 지웁니다.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('interactions/', views.place_interactions),
    path("health/", views.health_check),

    # 검색
    path("places/", views.place_list),
    path("map-search/", views.map_place_search),
    path("search/", views.recommendation_search),
    path("ai-search/candidates/", views.ai_recommendation_candidates),
    path("ai-search/", views.ai_recommendation_search),
    path("ai-web-search/", views.ai_web_search),
    path("search-safety/", views.search_safety_check),
    path("conversational-search-plan/", views.conversational_search_plan),
    path("kakao-place-tags/", views.kakao_place_tag_lookup),
    path("kakao-test/", views.kakao_search_test),

    # 장소 제보 (승인이 Place/PlaceTag 를 만들므로 Django 소유)
    path("place-reports/", views.place_reports),
    path("admin/place-reports/", views.admin_place_reports),
    path("admin/operations/", views.admin_operations_dashboard),
    path("admin/place-reports/<int:report_id>/", views.admin_place_report_detail),
    path("admin/place-reports/<int:report_id>/approve/", views.admin_place_report_approve),
    path("admin/place-reports/<int:report_id>/reject/", views.admin_place_report_reject),

    # 검색 개인화
    path("search-logs/", views.search_logs),
    path("search-logs/<int:search_log_id>/", views.search_log_detail),
    path("preference-tags/", views.preference_tags),
    path("preferences/", views.user_preferences),
    path("preferences/rebuild/", views.rebuild_preferences),
    path("preferences/<int:preference_id>/", views.user_preference_detail),
]
