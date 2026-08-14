import json
import os
import hashlib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework import serializers

from .models import (
    Place,
    PlaceInteractionEvent,
    PlaceReport,
    PlaceReportImage,
    UserPreference,
    UserSavedPlace,
    UserSearchLog,
)
from .services.user_preferences import normalize_preference_label, unique_valid_labels


ALLOWED_REPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_REPORT_IMAGE_SIZE = 5 * 1024 * 1024
MAX_REPORT_IMAGE_COUNT = 3
SAVED_PLACE_SOURCE_VALUES = {"local_db", "kakao", "web", "other"}
SAVED_PLACE_COORDINATE_QUANTIZER = Decimal("0.000001")


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


class PlaceInteractionEventSerializer(serializers.ModelSerializer):
    event_key = serializers.CharField(required=False, allow_blank=True, max_length=64)
    place_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    search_log_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = PlaceInteractionEvent
        fields = [
            'id',
            'event_key',
            'session_key',
            'search_id',
            'search_log_id',
            'event_type',
            'place_id',
            'place_key',
            'place_source',
            'place_external_id',
            'place_name',
            'place_category',
            'query',
            'requested_tags',
            'tag_name',
            'position',
            'context',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_requested_tags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('requested_tags must be a list.')
        return unique_valid_labels(value)[:20]

    def validate_context(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('context must be an object.')
        if len(json.dumps(value, ensure_ascii=False)) > 8192:
            raise serializers.ValidationError('context is too large.')
        return value

    def validate(self, attrs):
        event_type = attrs.get('event_type')
        tag_name = str(attrs.get('tag_name') or '').strip().lstrip('#')[:50]
        attrs['tag_name'] = tag_name
        attrs['query'] = str(attrs.get('query') or '').strip()[:255]
        attrs['search_id'] = str(attrs.get('search_id') or '').strip()[:64]
        attrs['place_key'] = str(attrs.get('place_key') or '').strip()[:255]
        attrs['place_source'] = str(attrs.get('place_source') or '').strip()[:50]
        attrs['place_external_id'] = str(
            attrs.get('place_external_id') or ''
        ).strip()[:100]
        attrs['place_name'] = str(attrs.get('place_name') or '').strip()[:200]
        attrs['place_category'] = str(
            attrs.get('place_category') or ''
        ).strip()[:100]

        if event_type in {'tag_confirm', 'tag_reject'} and not tag_name:
            raise serializers.ValidationError(
                {'tag_name': 'A tag is required for tag feedback.'}
            )
        if event_type == 'search' and not attrs['query']:
            raise serializers.ValidationError(
                {'query': 'A query is required for a search event.'}
            )
        if event_type not in {'search', 'clarification'} and not any([
            attrs.get('place_id'),
            attrs['place_key'],
            attrs['place_external_id'],
        ]):
            raise serializers.ValidationError(
                {'place_key': 'A place identity is required for this event.'}
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        raw_session_key = str(validated_data.pop('session_key', '') or '').strip()
        session_key = hashlib.sha256(raw_session_key.encode('utf-8')).hexdigest() \
            if raw_session_key else ''
        place_id = validated_data.pop('place_id', None)
        search_log_id = validated_data.pop('search_log_id', None)
        event_key = str(validated_data.pop('event_key', '') or '').strip()
        user = None
        if request is not None and getattr(request.user, 'is_authenticated', False):
            user = request.user

        place = None
        if place_id:
            place = Place.objects.filter(id=place_id).first()
        if place is None and validated_data.get('place_external_id'):
            place_query = Place.objects.filter(
                external_id=validated_data['place_external_id'],
            )
            if validated_data.get('place_source'):
                place_query = place_query.filter(
                    source=validated_data['place_source'],
                )
            place = place_query.first()

        search_log = None
        if search_log_id and user is not None:
            search_log = UserSearchLog.objects.filter(
                id=search_log_id,
                user=user,
            ).first()

        defaults = {
            **validated_data,
            'user': user,
            'session_key': session_key,
            'place': place,
            'search_log': search_log,
        }
        if event_key:
            event, _ = PlaceInteractionEvent.objects.get_or_create(
                event_key=event_key,
                defaults=defaults,
            )
            return event
        return PlaceInteractionEvent.objects.create(**defaults)


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


class UserSavedPlaceSerializer(serializers.ModelSerializer):
    place = serializers.IntegerField(source="place_id", read_only=True)
    place_id = serializers.PrimaryKeyRelatedField(
        queryset=Place.objects.all(),
        source="place",
        write_only=True,
        required=False,
        allow_null=True,
    )
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = UserSavedPlace
        fields = [
            "id",
            "place",
            "place_id",
            "place_key",
            "source",
            "source_label",
            "external_id",
            "name",
            "category",
            "address",
            "lat",
            "lng",
            "detail_url",
            "kakao_place_url",
            "phone",
            "memo",
            "raw",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "place", "place_key", "source_label", "created_at", "updated_at"]
        extra_kwargs = {
            "source": {"required": False},
            "external_id": {"required": False, "allow_blank": True},
            "name": {"required": False, "allow_blank": True},
            "category": {"required": False, "allow_blank": True},
            "address": {"required": False, "allow_blank": True},
            "lat": {"required": False, "allow_null": True},
            "lng": {"required": False, "allow_null": True},
            "detail_url": {"required": False, "allow_blank": True},
            "kakao_place_url": {"required": False, "allow_blank": True},
            "phone": {"required": False, "allow_blank": True},
            "memo": {"required": False, "allow_blank": True},
            "raw": {"required": False},
        }

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
            raise serializers.ValidationError("좌표를 숫자로 보내 주세요.")

        if not decimal_value.is_finite():
            raise serializers.ValidationError("좌표를 숫자로 보내 주세요.")

        minimum_value, maximum_value = (
            (Decimal("-90"), Decimal("90"))
            if field_name == "lat"
            else (Decimal("-180"), Decimal("180"))
        )
        if decimal_value < minimum_value or decimal_value > maximum_value:
            raise serializers.ValidationError("좌표 범위를 확인해 주세요.")

        return decimal_value.quantize(
            SAVED_PLACE_COORDINATE_QUANTIZER,
            rounding=ROUND_HALF_UP,
        )

    def to_internal_value(self, data):
        mutable_data = data.copy() if hasattr(data, "copy") else dict(data)
        camel_case_map = {
            "placeId": "place_id",
            "externalId": "external_id",
            "detailUrl": "detail_url",
            "kakaoPlaceUrl": "kakao_place_url",
        }
        for source_key, target_key in camel_case_map.items():
            if source_key in mutable_data and target_key not in mutable_data:
                mutable_data[target_key] = mutable_data[source_key]

        for coordinate_field in ["lat", "lng"]:
            if coordinate_field in mutable_data and mutable_data[coordinate_field] not in (None, ""):
                mutable_data[coordinate_field] = self.sanitize_coordinate_value(
                    mutable_data[coordinate_field],
                    coordinate_field,
                )

        return super().to_internal_value(mutable_data)

    def validate_source(self, value):
        value = self.sanitize_text_value(value, 30) or "other"
        return value if value in SAVED_PLACE_SOURCE_VALUES else "other"

    def validate_raw(self, value):
        return value if isinstance(value, dict) else {}

    def validate(self, attrs):
        instance = self.instance
        place = attrs.get("place") or getattr(instance, "place", None)

        if place:
            attrs.setdefault("source", "local_db")
            attrs["external_id"] = attrs.get("external_id") or place.external_id
            attrs["name"] = attrs.get("name") or place.name
            attrs["category"] = attrs.get("category") or place.category
            attrs["address"] = attrs.get("address") or place.address
            attrs["lat"] = attrs.get("lat") or self.sanitize_coordinate_value(place.lat, "lat")
            attrs["lng"] = attrs.get("lng") or self.sanitize_coordinate_value(place.lng, "lng")
            attrs["place_key"] = f"place:{place.id}"
        else:
            attrs["source"] = attrs.get("source") or getattr(instance, "source", "other")
            attrs["external_id"] = self.sanitize_text_value(
                attrs.get("external_id") or getattr(instance, "external_id", ""),
                100,
            )
            attrs["name"] = self.sanitize_text_value(
                attrs.get("name") or getattr(instance, "name", ""),
                200,
            )
            if not attrs["name"]:
                raise serializers.ValidationError({
                    "name": "저장할 장소명을 확인해 주세요.",
                })

            lat = attrs.get("lat", getattr(instance, "lat", None))
            lng = attrs.get("lng", getattr(instance, "lng", None))
            attrs["lat"] = self.sanitize_coordinate_value(lat, "lat") if lat not in (None, "") else None
            attrs["lng"] = self.sanitize_coordinate_value(lng, "lng") if lng not in (None, "") else None

            if attrs["external_id"]:
                attrs["place_key"] = f"{attrs['source']}:{attrs['external_id']}"
            else:
                attrs["place_key"] = (
                    f"snapshot:{attrs['source']}:{attrs['name']}:"
                    f"{attrs['lat'] or ''}:{attrs['lng'] or ''}"
                )

        attrs["category"] = self.sanitize_text_value(attrs.get("category"), 100)
        attrs["address"] = self.sanitize_text_value(attrs.get("address"), 255)
        attrs["detail_url"] = self.sanitize_text_value(attrs.get("detail_url"), 500)
        attrs["kakao_place_url"] = self.sanitize_text_value(attrs.get("kakao_place_url"), 500)
        attrs["phone"] = self.sanitize_text_value(attrs.get("phone"), 50)
        attrs["memo"] = self.sanitize_text_value(attrs.get("memo"), 2000)

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        place_key = validated_data.pop("place_key")
        saved_place, created = UserSavedPlace.objects.update_or_create(
            user=request.user,
            place_key=place_key,
            defaults=validated_data,
        )
        self.created = created
        return saved_place

    def update(self, instance, validated_data):
        validated_data.pop("place_key", None)
        validated_data.pop("place", None)
        for field_name in [
            "memo",
            "name",
            "category",
            "address",
            "lat",
            "lng",
            "detail_url",
            "kakao_place_url",
            "phone",
            "raw",
        ]:
            if field_name in validated_data:
                setattr(instance, field_name, validated_data[field_name])

        instance.save()
        return instance


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
