from django.contrib import admin
from django.urls import path, include
from boards import views as board_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("accounts.urls")),
    path("api/recommendations/", include("recommendations.urls")),
    path("api/boards/", include("boards.urls")),
    path("api/notifications/", board_views.notification_list),
    path("api/notifications/<int:notification_id>/read/", board_views.notification_read),
    path("api/notifications/read-all/", board_views.notification_read_all),
    path("api/inquiries/", board_views.inquiry_create),
    path("api/inquiries/my/", board_views.my_inquiry_list),
    path("api/inquiries/<int:inquiry_id>/", board_views.inquiry_detail),
    path("api/admin/inquiries/", board_views.admin_inquiry_list),
    path("api/admin/inquiries/<int:inquiry_id>/", board_views.admin_inquiry_update),
    path("api/admin/users/", board_views.admin_user_list),
    path("api/admin/users/<int:user_id>/", board_views.admin_user_detail),
    path("api/admin/users/<int:user_id>/penalties/", board_views.admin_create_user_penalty),
    path("api/admin/users/<int:user_id>/notifications/", board_views.admin_create_user_notification),
]
