import uuid

from django.conf import settings
from django.db import models


class AssistanceKind(models.TextChoices):
    DESIGN = "design_polish", "设计与资产说明"
    TEMPLATE = "template_generate", "生产模板"
    MISSION = "mission_write", "Mission 编写"
    REVIEW = "review_assist", "验收辅助"
    REQUIREMENTS = "agent_requirements", "Agent 需求文档"


class AgentDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    capabilities = models.JSONField(default=list)
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]


class AssistanceRequest(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待本地设备"
        RUNNING = "running", "本地处理中"
        SUCCEEDED = "succeeded", "候选已返回"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"
        EXPIRED = "expired", "已过期"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    device = models.ForeignKey(AgentDevice, on_delete=models.CASCADE, related_name="requests")
    kind = models.CharField(max_length=24, choices=AssistanceKind.choices)
    schema_version = models.PositiveSmallIntegerField(default=1)
    object_id = models.UUIDField(null=True, blank=True)
    base_version = models.PositiveIntegerField(null=True, blank=True)
    submission_id = models.UUIDField(null=True, blank=True)
    input = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    claimed_at = models.DateTimeField(null=True, blank=True)
    attempt_id = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    result = models.JSONField(null=True, blank=True)
    error = models.CharField(max_length=2048, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    idempotency_key = models.UUIDField()
    payload_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "idempotency_key"], name="agent_request_idempotency"),
            models.UniqueConstraint(fields=["device"], condition=models.Q(status="running"), name="agent_device_one_running"),
        ]
        indexes = [models.Index(fields=["owner", "status"]), models.Index(fields=["device", "status", "created_at"])]
