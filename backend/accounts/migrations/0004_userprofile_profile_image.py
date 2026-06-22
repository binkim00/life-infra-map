import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="profile_image",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="profile_images/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        ["jpg", "jpeg", "png", "gif", "webp"]
                    ),
                ],
                verbose_name="프로필 사진",
            ),
        ),
    ]
