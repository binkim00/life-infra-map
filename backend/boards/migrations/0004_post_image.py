import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0003_inquiry_notification_userpenalty_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="image",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="board_images/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        ["jpg", "jpeg", "png", "gif", "webp"]
                    ),
                ],
                verbose_name="첨부 이미지",
            ),
        ),
    ]
