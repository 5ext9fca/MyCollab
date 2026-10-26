import uuid

from django.conf import settings
from django.db import models


class FileTransfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_transfers")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, related_name="received_transfers")
    sender_token = models.CharField(max_length=64)
    receiver_token = models.CharField(max_length=64, blank=True)
    code_digest = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    received_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, default="waiting")
    offer = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    error = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    pair_expires_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(size__lte=100 * 1024 * 1024), name="transfer_size_limit"),
            models.CheckConstraint(condition=models.Q(status__in=["waiting", "paired", "accepted", "completed", "failed", "cancelled", "expired"]), name="transfer_status_valid"),
        ]
