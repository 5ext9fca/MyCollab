from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import RegistrationRequest, User


class UserBriefSerializer(serializers.ModelSerializer):
    """Minimal user representation embedded in mission payloads."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "display_name"]

    def get_display_name(self, obj: User) -> str:
        return obj.get_full_name() or obj.get_username()


class MeSerializer(UserBriefSerializer):
    """Current-session user, including fields the SPA needs for route guards."""

    class Meta(UserBriefSerializer.Meta):
        fields = UserBriefSerializer.Meta.fields + ["is_staff"]


class MemberSerializer(serializers.ModelSerializer):
    """Admin-facing member row (read-only list)."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "email",
            "is_active",
            "is_staff",
            "date_joined",
        ]

    def get_display_name(self, obj: User) -> str:
        return obj.get_full_name() or obj.get_username()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class RegisterSerializer(serializers.Serializer):
    """Public self-service registration input."""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    display_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_username(self, value: str) -> str:
        username = value.strip()
        if not username:
            raise serializers.ValidationError("用户名不能为空。")
        return username

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class RegistrationRequestSerializer(serializers.ModelSerializer):
    """Admin read model; never exposes the stored password hash."""

    reviewed_by = UserBriefSerializer(read_only=True)

    class Meta:
        model = RegistrationRequest
        fields = [
            "id",
            "username",
            "email",
            "display_name",
            "message",
            "status",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "created_at",
        ]


class RejectSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
