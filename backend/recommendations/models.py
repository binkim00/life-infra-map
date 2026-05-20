from django.db import models

# Create your models here.
from django.db import models


class Place(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50)
    address = models.CharField(max_length=255, blank=True)

    lat = models.FloatField()
    lng = models.FloatField()

    source = models.CharField(max_length=50)
    external_id = models.CharField(max_length=100, blank=True)

    source_name = models.CharField(max_length=100, blank=True)
    source_updated_at = models.DateField(null=True, blank=True)

    detail_location = models.CharField(max_length=255, blank=True)

    data_quality_status = models.CharField(
        max_length=30,
        default="candidate",
    )
    data_quality_score = models.IntegerField(default=50)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="unique_place_source_external_id",
            )
        ]

    def __str__(self):
        return self.name


class Tag(models.Model):
    TAG_TYPE_CHOICES = [
        ("category", "카테고리"),
        ("recommendation", "추천가치"),
        ("warning", "주의/확인필요"),
    ]

    name = models.CharField(max_length=50, unique=True)
    tag_type = models.CharField(
        max_length=30,
        choices=TAG_TYPE_CHOICES,
        default="recommendation",
    )
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class PlaceTag(models.Model):
    TAG_SOURCE_CHOICES = [
        ("category_rule", "카테고리 규칙"),
        ("runtime_rule", "실시간 추천 규칙"),
        ("external_data", "외부 데이터"),
        ("ai_suggested", "AI 후보"),
        ("team_checked", "팀 확인"),
        ("admin_checked", "관리자 확인"),
        ("user_verified", "사용자 검증"),
    ]

    TAG_STATUS_CHOICES = [
        ("confirmed", "확인됨"),
        ("candidate", "후보"),
        ("needs_verification", "확인 필요"),
        ("rejected", "반려"),
    ]

    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="place_tags",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="place_tags",
    )

    source = models.CharField(
        max_length=30,
        choices=TAG_SOURCE_CHOICES,
        default="external_data",
    )
    status = models.CharField(
        max_length=30,
        choices=TAG_STATUS_CHOICES,
        default="candidate",
    )
    confidence = models.IntegerField(default=50)
    evidence = models.TextField(blank=True)

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["place", "tag", "source"],
                name="unique_place_tag_source",
            )
        ]

    def __str__(self):
        return f"{self.place.name} - {self.tag.name}"