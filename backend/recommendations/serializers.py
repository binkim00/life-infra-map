from rest_framework import serializers

from .models import UserPreference, UserSearchLog
from .services.user_preferences import normalize_preference_label, unique_valid_labels


class UserSearchLogSerializer(serializers.ModelSerializer):
    list_json_fields = {
        "requested_conditions",
        "menu_keywords",
        "place_type_keywords",
        "preferred_tags",
        "negative_tags",
    }

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

    def to_internal_value(self, data):
        allowed = set(self.fields.keys()) - set(self.Meta.read_only_fields)
        filtered_data = {
            key: value
            for key, value in data.items()
            if key in allowed
        }
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
