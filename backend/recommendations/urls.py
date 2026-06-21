from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check),
    path("places/", views.place_list),
    path("kakao-place-tags/", views.kakao_place_tag_lookup),
    path("search/", views.recommendation_search),
    path("kakao-test/", views.kakao_search_test),
]
