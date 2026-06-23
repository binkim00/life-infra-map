from django.urls import path
from . import views

urlpatterns = [
    path("posts/", views.post_list_create),
    path("posts/<int:post_id>/", views.post_detail_update_delete),
    path("posts/<int:post_id>/comments/", views.comment_create),
    path("posts/<int:post_id>/like/", views.toggle_post_like),
    path("posts/<int:post_id>/report/", views.report_post),
    path("comments/<int:comment_id>/", views.comment_update_delete),
    path("comments/<int:comment_id>/like/", views.toggle_comment_like),
    path("comments/<int:comment_id>/dislike/", views.toggle_comment_dislike),
    path("comments/<int:comment_id>/report/", views.report_comment),
    path("reports/", views.report_list),
    path("reports/<int:report_id>/process/", views.process_report),
]
