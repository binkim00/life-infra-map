from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check),
    path("places/", views.place_list),
    path("map-search/", views.map_place_search),
    path("kakao-place-tags/", views.kakao_place_tag_lookup),
    path("search/", views.recommendation_search),
    path("search-safety/", views.search_safety_check),
    path("conversational-search-plan/", views.conversational_search_plan),
    path("search-logs/", views.search_logs),
    path("search-logs/<int:search_log_id>/", views.search_log_detail),
    path("preference-tags/", views.preference_tags),
    path("preferences/", views.user_preferences),
    path("preferences/rebuild/", views.rebuild_preferences),
    path("preferences/<int:preference_id>/", views.user_preference_detail),
    path("place-reports/", views.place_reports),
    path("admin/place-reports/", views.admin_place_reports),
    path("admin/place-reports/<int:report_id>/", views.admin_place_report_detail),
    path("admin/place-reports/<int:report_id>/approve/", views.admin_place_report_approve),
    path("admin/place-reports/<int:report_id>/reject/", views.admin_place_report_reject),
    path("ai-search/", views.ai_recommendation_search),
    path("ai-web-search/", views.ai_web_search),
    path("kakao-test/", views.kakao_search_test),
]
