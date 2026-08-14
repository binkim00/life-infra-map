import uuid

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
            # 지도 검색은 카테고리 없이 좌표 범위만으로 후보를 좁히는 경우가 많습니다.
            models.Index(fields=["lat", "lng"]),
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

        # 검색 결과 클릭·저장·거절을 여러 익명 주체에 걸쳐 집계한 약한 후보 신호입니다.
        ("interaction_signal", "검색 행동 기반 후보 태그"),

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


class DataSourceSyncRun(models.Model):
    SYNC_TYPE_CHOICES = [("full", "Full snapshot"), ("delta", "Delta")]
    STATUS_CHOICES = [
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    source = models.CharField(max_length=50)
    dataset = models.CharField(max_length=100)
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPE_CHOICES, default="full")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    source_uri = models.TextField(blank=True)
    source_checksum = models.CharField(max_length=64, blank=True)
    cursor = models.JSONField(default=dict, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "dataset", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.source}:{self.dataset} ({self.status})"


class SourcePlaceRecord(models.Model):
    """Source-owned place row before normalization, geocoding, and deduplication."""

    source = models.CharField(max_length=50)
    dataset = models.CharField(max_length=100)
    source_record_id = models.CharField(max_length=160)
    name = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=100, blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    business_status = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    address = models.CharField(max_length=500, blank=True)
    road_address = models.CharField(max_length=500, blank=True)
    sido_name = models.CharField(max_length=50, blank=True)
    sigungu_name = models.CharField(max_length=80, blank=True)
    administrative_code = models.CharField(max_length=30, blank=True)
    source_x = models.CharField(max_length=50, blank=True)
    source_y = models.CharField(max_length=50, blank=True)
    coordinate_reference_system = models.CharField(max_length=30, blank=True)
    license_date = models.DateField(null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    normalized_place = models.ForeignKey(
        Place,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_records",
    )
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "dataset", "source_record_id"],
                name="unique_source_place_record",
            )
        ]
        indexes = [
            models.Index(fields=["source", "dataset", "is_active"]),
            models.Index(fields=["sido_name", "sigungu_name", "category"]),
            models.Index(fields=["normalized_place"]),
        ]

    def __str__(self):
        return self.name or f"{self.source}:{self.source_record_id}"


def new_evidence_key():
    return uuid.uuid4().hex


class PlaceTagEvidence(models.Model):
    POLARITY_CHOICES = [
        ("positive", "Positive"),
        ("negative", "Negative"),
        ("neutral", "Neutral"),
    ]

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="tag_evidence")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="place_evidence")
    evidence_key = models.CharField(
        max_length=64,
        unique=True,
        default=new_evidence_key,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="place_tag_evidence",
    )
    source = models.CharField(max_length=50)
    source_reference = models.CharField(max_length=500, blank=True)
    polarity = models.CharField(max_length=20, choices=POLARITY_CHOICES, default="positive")
    confidence = models.PositiveSmallIntegerField(default=50)
    evidence = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["place", "tag", "polarity"]),
            models.Index(fields=["source", "-observed_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.place} - {self.tag} ({self.polarity})"


class PlaceCoverage(models.Model):
    """Materialized nationwide coverage metrics by administrative area and category."""

    administrative_code = models.CharField(max_length=30)
    sido_name = models.CharField(max_length=50, blank=True)
    sigungu_name = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=100)
    source = models.CharField(max_length=50, blank=True)
    source_record_count = models.PositiveIntegerField(default=0)
    active_record_count = models.PositiveIntegerField(default=0)
    normalized_place_count = models.PositiveIntegerField(default=0)
    tagged_place_count = models.PositiveIntegerField(default=0)
    evidence_place_count = models.PositiveIntegerField(default=0)
    coverage_score = models.FloatField(default=0)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["administrative_code", "category", "source"],
                name="unique_place_coverage_cell",
            )
        ]
        indexes = [
            models.Index(fields=["sido_name", "sigungu_name", "category"]),
            models.Index(fields=["coverage_score"]),
        ]

    def __str__(self):
        return f"{self.administrative_code}:{self.category} ({self.coverage_score:.1f})"


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


class PlaceInteractionEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('search', 'Search demand'),
        ('clarification', 'Clarification answer'),
        ('impression', 'Result impression'),
        ('click', 'Result click'),
        ('save', 'Place save'),
        ('dismiss', 'Result rejection'),
        ('tag_confirm', 'Tag confirmed'),
        ('tag_reject', 'Tag rejected'),
    ]

    event_key = models.CharField(
        max_length=64,
        unique=True,
        default=new_evidence_key,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='place_interactions',
    )
    session_key = models.CharField(max_length=64, blank=True)
    search_id = models.CharField(max_length=64, blank=True)
    search_log = models.ForeignKey(
        UserSearchLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interactions',
    )
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    place = models.ForeignKey(
        Place,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interaction_events',
    )
    place_key = models.CharField(max_length=255, blank=True)
    place_source = models.CharField(max_length=50, blank=True)
    place_external_id = models.CharField(max_length=100, blank=True)
    place_name = models.CharField(max_length=200, blank=True)
    place_category = models.CharField(max_length=100, blank=True)
    query = models.CharField(max_length=255, blank=True)
    requested_tags = models.JSONField(default=list, blank=True)
    tag_name = models.CharField(max_length=50, blank=True)
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['search_id', 'event_type']),
            models.Index(fields=['place', 'event_type', '-created_at']),
            models.Index(fields=['tag_name', 'event_type', '-created_at']),
            models.Index(fields=['session_key', '-created_at']),
        ]

    def __str__(self):
        target = self.place_name or self.place_key or self.query
        return '{}: {}'.format(self.event_type, target)


class TagEnrichmentRequest(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name='tag_enrichment_requests',
    )
    tag_name = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    priority = models.PositiveIntegerField(default=1)
    demand_count = models.PositiveIntegerField(default=1)
    source_query = models.CharField(max_length=255, blank=True)
    context = models.JSONField(default=dict, blank=True)
    last_requested_at = models.DateTimeField(auto_now=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['place', 'tag_name'],
                name='unique_place_tag_enrichment_request',
            ),
        ]
        indexes = [
            models.Index(fields=['status', '-priority', 'created_at']),
            models.Index(fields=['tag_name', 'status']),
        ]

    def __str__(self):
        return '{} - {} ({})'.format(self.place.name, self.tag_name, self.status)


class UserPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    preference_type = models.CharField(max_length=30)
    key = models.CharField(max_length=100)
    label = models.CharField(max_length=100)

    score = models.FloatField(default=0)
    search_count = models.PositiveIntegerField(default=0)

    source = models.CharField(max_length=30, default="search_log")

    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "preference_type", "key"],
                name="unique_user_preference",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-score"]),
            models.Index(fields=["preference_type", "key"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.preference_type}:{self.label}"


class UserSavedPlace(models.Model):
    SOURCE_CHOICES = [
        ("local_db", "저장 장소"),
        ("kakao", "카카오 장소"),
        ("web", "웹 참고"),
        ("other", "기타"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_places",
    )
    place = models.ForeignKey(
        "Place",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_by_users",
    )

    place_key = models.CharField(max_length=255)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default="local_db")
    external_id = models.CharField(max_length=100, blank=True)

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    detail_url = models.URLField(max_length=500, blank=True)
    kakao_place_url = models.URLField(max_length=500, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    memo = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "place_key"],
                name="unique_user_saved_place_key",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["user", "source"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.name}"


class PlaceReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ("new_place", "장소 추가 제보"),
        ("edit_place", "장소 정보 수정 제보"),
        ("tag_suggestion", "태그 추가 제보"),
        ("wrong_info", "잘못된 정보 제보"),
    ]

    STATUS_CHOICES = [
        ("pending", "검토 대기"),
        ("approved", "승인"),
        ("rejected", "반려"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="place_reports",
    )
    place = models.ForeignKey(
        "Place",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )

    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    suggested_name = models.CharField(max_length=255, blank=True)
    suggested_category = models.CharField(max_length=50, blank=True)
    suggested_address = models.CharField(max_length=255, blank=True)
    suggested_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    suggested_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    suggested_tags = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)

    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_place_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["report_type"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.report_type} ({self.status})"


class PlaceReportImage(models.Model):
    report = models.ForeignKey(
        PlaceReport,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="place_reports/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name or f"report-image-{self.id}"
