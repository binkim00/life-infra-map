from django.conf import settings
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

    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "lat", "lng"]),
        ]
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
        # default_tags 같은 카테고리 기반 기본 태그를 저장해야 할 때 사용합니다.
        # 너무 기본적인 태그는 저장하지 않고, 추천/필터에 필요한 태그만 저장하는 방향입니다.
        ("category_rule", "카테고리 기반 기본 태그"),

        # 공공데이터 원본 필드에서 바로 판단 가능한 태그입니다.
        # 예: 무료 여부, 개방 여부, 시설 구분 등
        ("field_rule", "원본 필드 기반 태그"),

        # 장소명, 시설명, 주소, 설명 등의 문자열 키워드로 붙인 태그입니다.
        ("keyword_rule", "키워드 규칙 기반 태그"),

        # 네이버 블로그 검색 결과 등을 바탕으로 만든 후보 태그입니다.
        ("blog_search", "블로그 검색 기반 후보 태그"),

        # 카카오, 관광공사 등 외부 API 응답을 바탕으로 만든 태그입니다.
        ("external_api", "외부 API 기반 태그"),

        # 공공데이터, CSV, 지자체 파일 등 외부 원본 데이터 기반 태그입니다.
        ("external_data", "외부 데이터 기반 태그"),

        # AI가 장소명, 설명, 카테고리 등을 보고 추천한 후보 태그입니다.
        ("ai_suggested", "AI 추천 후보 태그"),

        # 팀 검수와 관리자 검수를 하나로 합친 값입니다.
        ("checked", "검수 완료 태그"),

        # 서비스 운영 후 사용자가 맞다고 검증한 태그입니다.
        ("user_verified", "사용자 검증 태그"),

        # warning_tags처럼 정보 부족 또는 확인 필요 목적으로 저장하는 태그입니다.
        ("warning_tags", "확인 필요 태그"),
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
        max_length=50,
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

    @property
    def source_label(self):
        return dict(self.TAG_SOURCE_CHOICES).get(self.source, self.source)

    @property
    def status_label(self):
        return dict(self.TAG_STATUS_CHOICES).get(self.status, self.status)


class UserSearchLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_logs",
    )
    query = models.CharField(max_length=255)
    search_mode = models.CharField(max_length=50, blank=True)
    scenario = models.CharField(max_length=50, blank=True)
    location_hint = models.CharField(max_length=100, blank=True)

    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    target_query = models.CharField(max_length=255, blank=True)
    category_hint = models.CharField(max_length=50, blank=True)

    requested_conditions = models.JSONField(default=list, blank=True)
    menu_keywords = models.JSONField(default=list, blank=True)
    place_type_keywords = models.JSONField(default=list, blank=True)
    preferred_tags = models.JSONField(default=list, blank=True)
    negative_tags = models.JSONField(default=list, blank=True)

    result_count = models.PositiveIntegerField(default=0)
    db_result_count = models.PositiveIntegerField(default=0)
    kakao_result_count = models.PositiveIntegerField(default=0)
    ai_web_result_count = models.PositiveIntegerField(default=0)

    search_plan_snapshot = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["scenario"]),
            models.Index(fields=["category_hint"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.query}"
