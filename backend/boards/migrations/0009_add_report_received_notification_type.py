from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0008_remove_comment_author_hearted"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("post_commented", "게시글 댓글"),
                    ("post_liked", "게시글 좋아요"),
                    ("comment_liked", "댓글 좋아요"),
                    ("report_received", "신고 접수"),
                    ("report_passed", "신고 패스"),
                    ("report_penalty", "신고 조치"),
                    ("admin_warning", "관리자 경고"),
                    ("inquiry_answered", "문의 답변"),
                    ("penalty_notice", "제재 안내"),
                    ("system", "시스템"),
                ],
                default="system",
                max_length=30,
                verbose_name="알림 종류",
            ),
        ),
    ]
