from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from rest_framework import serializers

from .models import UserProfile
from .utils import get_user_tier_info


def get_file_url(serializer, file_field):
    if not file_field:
        return ""

    request = serializer.context.get("request")
    url = file_field.url

    if request:
        return request.build_absolute_uri(url)

    return url


def make_unique_nickname(base):
    nickname = (base or "user").strip()[:50] or "user"

    if not UserProfile.objects.filter(nickname=nickname).exists():
        return nickname

    prefix = nickname[:43]
    index = 1

    while UserProfile.objects.filter(nickname=f"{prefix}-{index}").exists():
        index += 1

    return f"{prefix}-{index}"


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "nickname": make_unique_nickname(user.username),
        },
    )
    return profile


class UserSerializer(serializers.ModelSerializer):
    nickname = serializers.SerializerMethodField()
    profile_image_url = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    tier = serializers.SerializerMethodField()
    tier_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "nickname",
            "profile_image_url",
            "email",
            "is_staff",
            "score",
            "tier",
            "tier_label",
            "date_joined",
        ]

    def get_nickname(self, obj):
        return get_or_create_profile(obj).nickname

    def get_profile_image_url(self, obj):
        return get_file_url(self, get_or_create_profile(obj).profile_image)

    def get_score(self, obj):
        return get_user_tier_info(obj)["score"]

    def get_tier(self, obj):
        return get_user_tier_info(obj)["tier"]

    def get_tier_label(self, obj):
        return get_user_tier_info(obj)["tier_label"]


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    nickname = serializers.CharField(max_length=50)
    profile_image = serializers.FileField(
        required=False,
        allow_null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "gif", "webp"]),
        ],
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("이미 사용 중인 아이디입니다.")
        return value

    def validate_nickname(self, value):
        nickname = value.strip()

        if not nickname:
            raise serializers.ValidationError("닉네임을 입력해주세요.")

        if UserProfile.objects.filter(nickname=nickname).exists():
            raise serializers.ValidationError("이미 사용 중인 닉네임입니다.")

        return nickname

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({
                "password_confirm": "비밀번호가 일치하지 않습니다.",
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        nickname = validated_data.pop("nickname")
        profile_image = validated_data.pop("profile_image", None)

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        UserProfile.objects.create(
            user=user,
            nickname=nickname,
            profile_image=profile_image,
        )

        return user


class NicknameUpdateSerializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=50)

    def validate_nickname(self, value):
        nickname = value.strip()

        if not nickname:
            raise serializers.ValidationError("닉네임을 입력해주세요.")

        user = self.context["request"].user
        exists = UserProfile.objects.filter(nickname=nickname).exclude(user=user).exists()

        if exists:
            raise serializers.ValidationError("이미 사용 중인 닉네임입니다.")

        return nickname

    def save(self, **kwargs):
        user = self.context["request"].user
        profile = get_or_create_profile(user)
        profile.nickname = self.validated_data["nickname"]
        profile.save(update_fields=["nickname", "updated_at"])
        return profile


class ProfileImageUpdateSerializer(serializers.Serializer):
    profile_image = serializers.FileField(
        required=False,
        allow_null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "gif", "webp"]),
        ],
    )

    def save(self, **kwargs):
        user = self.context["request"].user
        profile = get_or_create_profile(user)
        profile.profile_image = self.validated_data.get("profile_image")
        profile.save(update_fields=["profile_image", "updated_at"])
        return profile


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            username=attrs["username"],
            password=attrs["password"],
        )

        if user is None:
            raise serializers.ValidationError("아이디 또는 비밀번호가 올바르지 않습니다.")

        attrs["user"] = user
        return attrs
