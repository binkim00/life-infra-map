from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0007_comment_author_hearted_commentdislike"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="comment",
            name="author_hearted",
        ),
    ]
