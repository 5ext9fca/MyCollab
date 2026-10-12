import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Team member.

    The initial version maps one Django user to one team member. Extra profile
    fields can be added here later without a painful user-model migration.
    """

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.get_username()


class RegistrationStatus(models.TextChoices):
    PENDING = "Pending", "待审批"
    APPROVED = "Approved", "已通过"
    REJECTED = "Rejected", "已拒绝"


class RegistrationRequest(models.Model):
    """A self-service registration awaiting administrator approval.

    The plaintext password is never stored: the submitted password is hashed
    immediately and only copied onto the ``User`` when an admin approves the
    request. Keeping pending sign-ups out of ``auth_user`` avoids username
    squatting by unapproved applicants and keeps the active member list clean.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    display_name = models.CharField(max_length=150, blank=True)
    password_hash = models.CharField(max_length=256)
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.PENDING,
    )
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_registrations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["username"],
                condition=models.Q(status=RegistrationStatus.PENDING),
                name="accounts_unique_pending_username",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.username} ({self.status})"
