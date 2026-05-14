from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check),
    path("search/", views.recommendation_search),
    path("kakao-test/", views.kakao_search_test),
]