from django.urls import path
from . import views

urlpatterns = [
    path("signup/", views.signup),
    path("login/", views.login),
    path("logout/", views.logout),
    path("me/", views.me),
    path("me/nickname/", views.update_nickname),
    path("me/profile-image/", views.update_profile_image),
    path("mypage/", views.mypage),
]
