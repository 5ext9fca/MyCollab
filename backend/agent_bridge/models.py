import uuid

from django.conf import settings
from django.db import models


class AssistanceKind(models.TextChoices):
    DESIGN = "design_polish", "设计与资产说明"
    TEMPLATE = "template_generate", "生产模板"
    MISSION = "mission_write", "Mission 编写"
    REVIEW = "review_assist", "验收辅助"
    IMAGE_GENERATE = "image_generate", "图像生成"
    IMAGE_EDIT = "image_edit", "图像编辑"
    CODE = "code_implement", "代码实现"


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
        AWAITING_SELECTION = "awaiting_selection", "等待本地选择"
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
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED)
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


class InteractionSession(models.Model):
    """当前 attempt 的交互能力；不保存本机 Agent session 标识。"""
    request = models.OneToOneField(AssistanceRequest, on_delete=models.CASCADE, related_name='interaction')
    attempt_id = models.UUIDField()
    session_nonce = models.UUIDField()
    supports_followup = models.BooleanField(default=False)
    supports_permissions = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    event_count = models.PositiveIntegerField(default=0)
    event_bytes = models.PositiveIntegerField(default=0)
    command_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class InteractionEvent(models.Model):
    session = models.ForeignKey(InteractionSession, on_delete=models.CASCADE, related_name='events')
    event_id = models.UUIDField()
    seq = models.PositiveIntegerField()
    kind = models.CharField(max_length=32)
    payload = models.JSONField()
    payload_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seq']
        constraints = [
            models.UniqueConstraint(fields=['session', 'event_id'], name='interaction_event_dedup'),
            models.UniqueConstraint(fields=['session', 'seq'], name='interaction_event_sequence'),
        ]


class InteractionPermission(models.Model):
    session = models.ForeignKey(InteractionSession, on_delete=models.CASCADE, related_name='permissions')
    permission_id = models.UUIDField()
    operation = models.JSONField()
    operation_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='pending')
    decision = models.CharField(max_length=8, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'permission_id'], name='interaction_permission_dedup')]


class InteractionCommand(models.Model):
    session = models.ForeignKey(InteractionSession, on_delete=models.CASCADE, related_name='commands')
    command_id = models.UUIDField()
    kind = models.CharField(max_length=24)
    payload = models.JSONField()
    payload_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='queued')
    expires_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [models.UniqueConstraint(fields=['session', 'command_id'], name='interaction_command_dedup')]
