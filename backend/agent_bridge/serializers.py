from rest_framework import serializers

from .models import AgentDevice, AssistanceRequest
from . import protocol, services


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("包含未知字段或不是 JSON 对象。")
        return super().to_internal_value(data)


class DeviceCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100)
    capabilities = serializers.ListField(child=serializers.ChoiceField(choices=protocol.KINDS), min_length=1, max_length=5)
    expires_days = serializers.IntegerField(min_value=1, max_value=90, default=30)


class RequestCreateSerializer(StrictSerializer):
    device_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=protocol.KINDS)
    idempotency_key = serializers.UUIDField()
    draft = serializers.JSONField()
    instructions = serializers.CharField(max_length=10000, allow_blank=True, default="")
    context_ids = serializers.ListField(child=serializers.UUIDField(), max_length=20, default=list)
    comment_ids = serializers.ListField(child=serializers.UUIDField(), max_length=20, default=list)
    parent_id = serializers.UUIDField(allow_null=True, default=None)
    object_id = serializers.UUIDField(allow_null=True, default=None)
    base_version = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    submission_id = serializers.UUIDField(allow_null=True, default=None)
    retry_of = serializers.UUIDField(allow_null=True, default=None)


class HeartbeatSerializer(StrictSerializer):
    attempt_id = serializers.UUIDField()
    stopped = serializers.BooleanField(default=False)


class ResultSerializer(StrictSerializer):
    attempt_id = serializers.UUIDField()
    result = serializers.JSONField(required=False, default=None, allow_null=True)
    error = serializers.ChoiceField(choices=("", "model_timeout", "model_unavailable", "invalid_result", "local_configuration", "local_failure"), default="")


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentDevice
        fields = ("id", "name", "capabilities", "expires_at", "revoked_at", "last_seen_at", "created_at")


class RequestSerializer(serializers.ModelSerializer):
    stale_reason = serializers.SerializerMethodField()

    def get_stale_reason(self, obj):
        return services.stale_reason(obj)

    class Meta:
        model = AssistanceRequest
        fields = ("id", "device_id", "kind", "schema_version", "object_id", "base_version", "submission_id",
                  "input", "status", "attempt_id", "lease_expires_at", "expires_at", "result", "error",
                  "stopped_at", "retry_of_id", "created_at", "updated_at", "stale_reason")


class RequestSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistanceRequest
        fields = ("id", "kind", "status", "error", "stopped_at", "created_at")
