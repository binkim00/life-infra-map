import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework import serializers

from .models import Place, PlaceReport, PlaceReportImage, UserPreference, UserSearchLog
from .services.user_preferences import normalize_preference_label, unique_valid_labels


ALLOWED_REPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_REPORT_IMAGE_SIZE = 5 * 1024 * 1024
MAX_REPORT_IMAGE_COUNT = 3


def parse_label_list(value):
    if value in (None, ""):
        return []

    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return []

        if stripped_value.startswith("["):
            try:
                parsed = json.loads(stripped_value)
            except json.JSONDecodeError:
                parsed = []
            return unique_valid_labels(parsed)

        return unique_valid_labels([
            item.strip()
            for item in stripped_value.split(",")
        ])

    return unique_valid_labels(value if isinstance(value, list) else [value])


def validate_report_images(files):
    if len(files) > MAX_REPORT_IMAGE_COUNT:
        raise serializers.ValidationError(
            f"이미지는 최대 {MAX_REPORT_IMAGE_COUNT}장까지 첨부할 수 있습니다."
        )

    for file in files:
        extension = os.path.splitext(file.name or "")[1].lower()
        if extension not in ALLOWED_REPORT_IMAGE_EXTENSIONS:
            raise serializers.ValidationError("jpg, jpeg, png, webp 이미지만 첨부할 수 있습니다.")
        if file.size > MAX_REPORT_IMAGE_SIZE:
            raise serializers.ValidationError("이미지는 1개당 최대 5MB까지 첨부할 수 있습니다.")


class UserSearchLogSerializer(serializers.ModelSerializer):
    list_json_fields = {
        "requested_conditions",
        "menu_keywords",
        "place_type_keywords",
        "preferred_tags",
        "negative_tags",
    }
    coordinate_fields = {"lat", "lng"}
    count_fields = {
        "result_count",
        "db_result_count",
        "kakao_result_count",
        "ai_web_result_count",
    }
    text_field_max_lengths = {
        "query": 255,
        "search_mode": 50,
        "scenario": 50,
        "location_hint": 100,
        "target_query": 255,
        "category_hint": 50,
    }
    coordinate_quantizer = Decimal("0.000001")

    class Meta:
        model = UserSearchLog
        fields = [
            "id",
            "query",
            "search_mode",
            "scenario",
            "location_hint",
            "lat",
            "lng",
            "target_query",
            "category_hint",
            "requested_conditions",
            "menu_keywords",
            "place_type_keywords",
            "preferred_tags",
            "negative_tags",
            "result_count",
            "db_result_count",
            "kakao_result_count",
            "ai_web_result_count",
            "search_plan_snapshot",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def sanitize_text_value(self, value, max_length):
        if value is None:
            return ""

        return str(value).strip()[:max_length]

    def sanitize_coordinate_value(self, value, field_name):
        if value in (None, ""):
            return None

        try:
            decimal_value = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None

        if not decimal_value.is_finite():
            return None

        minimum_value, maximum_value = (
            (Decimal("-90"), Decimal("90"))
            if field_name == "lat"
            else (Decimal("-180"), Decimal("180"))
        )
        if decimal_value < minimum_value or decimal_value > maximum_value:
            return None

        return decimal_value.quantize(
            self.coordinate_quantizer,
            rounding=ROUND_HALF_UP,
        )

    def sanitize_count_value(self, value):
        if value in (None, ""):
            return 0

        try:
            numeric_value = int(Decimal(str(value).strip()))
        except (InvalidOperation, ValueError):
            return 0

        return max(numeric_value, 0)

    def to_internal_value(self, data):
        allowed = set(self.fields.keys()) - set(self.Meta.read_only_fields)
        filtered_data = {
            key: value
            for key, value in data.items()
            if key in allowed
        }

        for field_name, max_length in self.text_field_max_lengths.items():
            if field_name in filtered_data:
                filtered_data[field_name] = self.sanitize_text_value(
                    filtered_data[field_name],
                    max_length,
                )

        for field_name in self.coordinate_fields:
            if field_name in filtered_data:
                filtered_data[field_name] = self.sanitize_coordinate_value(
                    filtered_data[field_name],
                    field_name,
                )

        for field_name in self.count_fields:
            if field_name in filtered_data:
                filtered_data[field_name] = self.sanitize_count_value(
                    filtered_data[field_name],
                )

        for field_name in self.list_json_fields:
            if field_name in filtered_data:
                filtered_data[field_name] = parse_label_list(filtered_data[field_name])

        snapshot = filtered_data.get("search_plan_snapshot")
        if snapshot is not None and not isinstance(snapshot, dict):
            filtered_data["search_plan_snapshot"] = {}

        return super().to_internal_value(filtered_data)

    def validate_query(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("검색어를 입력해 주세요.")
        return value

    def validate(self, attrs):
        for field_name in self.list_json_fields:
            value = attrs.get(field_name)
            if value is not None and not isinstance(value, list):
                raise serializers.ValidationError({
                    field_name: "리스트 형태로 보내 주세요.",
                })
            if value is not None:
                attrs[field_name] = unique_valid_labels(value)

        snapshot = attrs.get("search_plan_snapshot")
        if snapshot is not None and not isinstance(snapshot, dict):
            raise serializers.ValidationError({
                "search_plan_snapshot": "객체 형태로 보내 주세요.",
            })

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        return UserSearchLog.objects.create(
            user=request.user,
            **validated_data,
        )


class UserSearchLogListSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSearchLog
        fields = [
            "id",
            "query",
            "search_mode",
            "scenario",
            "location_hint",
            "target_query",
            "category_hint",
            "requested_conditions",
            "menu_keywords",
            "place_type_keywords",
            "preferred_tags",
            "negative_tags",
            "result_count",
            "db_result_count",
            "kakao_result_count",
            "ai_web_result_count",
            "created_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field_name in [
            "requested_conditions",
            "menu_keywords",
            "place_type_keywords",
            "preferred_tags",
            "negative_tags",
        ]:
            data[field_name] = unique_valid_labels(data.get(field_name))

        data["category_hint"] = normalize_preference_label(data.get("category_hint"))
        data["scenario"] = normalize_preference_label(data.get("scenario"))
        data["target_query"] = normalize_preference_label(data.get("target_query"))
        return data


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = [
            "id",
            "preference_type",
            "key",
            "label",
            "score",
            "search_count",
            "source",
            "last_seen_at",
        ]


class PlaceReportImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PlaceReportImage
        fields = [
            "id",
            "image_url",
            "original_name",
            "created_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return ""

        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class PlaceReportCreateSerializer(serializers.ModelSerializer):
    place = serializers.PrimaryKeyRelatedField(
        queryset=Place.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PlaceReport
        fields = [
            "id",
            "place",
            "report_type",
            "suggested_name",
            "suggested_category",
            "suggested_address",
            "suggested_lat",
            "suggested_lng",
            "suggested_tags",
            "description",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def to_internal_value(self, data):
        allowed = set(self.fields.keys()) - set(self.Meta.read_only_fields)
        filtered_data = {}

        for key in allowed:
            if key == "suggested_tags":
                if hasattr(data, "getlist"):
                    values = data.getlist(key)
                    filtered_data[key] = parse_label_list(values if len(values) > 1 else (values[0] if values else []))
                else:
                    filtered_data[key] = parse_label_list(data.get(key))
            elif key in data:
                value = data.get(key)
                filtered_data[key] = None if value == "" and key in {"place", "suggested_lat", "suggested_lng"} else value

        return super().to_internal_value(filtered_data)

    def validate(self, attrs):
        request = self.context.get("request")
        files = request.FILES.getlist("images") if request else []
        validate_report_images(files)
        attrs["suggested_tags"] = unique_valid_labels(attrs.get("suggested_tags", []))
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        report = PlaceReport.objects.create(
            user=request.user,
            status="pending",
            **validated_data,
        )

        for file in request.FILES.getlist("images"):
            PlaceReportImage.objects.create(
                report=report,
                image=file,
                original_name=file.name[:255],
            )

        return report


class PlaceReportListSerializer(serializers.ModelSerializer):
    report_type_label = serializers.CharField(source="get_report_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    place_name = serializers.SerializerMethodField()
    image_count = serializers.IntegerField(source="images.count", read_only=True)

    class Meta:
        model = PlaceReport
        fields = [
            "id",
            "report_type",
            "report_type_label",
            "status",
            "status_label",
            "place",
            "place_name",
            "suggested_name",
            "suggested_tags",
            "admin_note",
            "image_count",
            "created_at",
            "reviewed_at",
        ]

    def get_place_name(self, obj):
        if obj.place:
            return obj.place.name
        return obj.suggested_name


class PlaceReportDetailSerializer(serializers.ModelSerializer):
    report_type_label = serializers.CharField(source="get_report_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    place_name = serializers.SerializerMethodField()
    user_username = serializers.CharField(source="user.username", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True)
    images = PlaceReportImageSerializer(many=True, read_only=True)

    class Meta:
        model = PlaceReport
        fields = [
            "id",
            "user",
            "user_username",
            "place",
            "place_name",
            "report_type",
            "report_type_label",
            "status",
            "status_label",
            "suggested_name",
            "suggested_category",
            "suggested_address",
            "suggested_lat",
            "suggested_lng",
            "suggested_tags",
            "description",
            "admin_note",
            "reviewed_by",
            "reviewed_by_username",
            "reviewed_at",
            "images",
            "created_at",
            "updated_at",
        ]

    def get_place_name(self, obj):
        if obj.place:
            return obj.place.name
        return obj.suggested_name


class PlaceReportAdminReviewSerializer(serializers.Serializer):
    admin_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
