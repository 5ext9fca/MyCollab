import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class MissionStatus(models.TextChoices):
    OPEN = "Open", "待认领"
    IN_PROGRESS = "InProgress", "进行中"
    SUBMITTED = "Submitted", "待验收"
    DONE = "Done", "已完成"
    CANCELLED = "Cancelled", "已取消"


#: Statuses that require a non-null assignee.
ASSIGNEE_REQUIRED_STATUSES = [
    MissionStatus.IN_PROGRESS,
    MissionStatus.SUBMITTED,
    MissionStatus.DONE,
]


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Mission(models.Model):
    """A task unit. Parent/child links express decomposition only.

    Every node stores its own content, creator, assignee and status; claiming a
    parent does not touch its children and vice versa.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    acceptance_criteria = models.TextField(blank=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_missions",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_missions",
        null=True,
        blank=True,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=MissionStatus.choices, default=MissionStatus.OPEN)
    result = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    tags = models.ManyToManyField(Tag, related_name="missions", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["creator", "-created_at"]),
            models.Index(fields=["parent"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status=MissionStatus.OPEN, assignee__isnull=True)
                    | Q(status__in=ASSIGNEE_REQUIRED_STATUSES, assignee__isnull=False)
                    | Q(status=MissionStatus.CANCELLED)
                ),
                name="mission_assignee_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(parent=models.F("id")),
                name="mission_parent_not_self",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Comment(models.Model):
    """A discussion note attached to a Mission.

    ``content`` uses the same field definition as ``Mission.content`` (Markdown
    text, blank allowed). Any team member may post a comment on any mission in
    any status; only the author may edit or delete their own comment.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mission_comments",
    )
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["mission", "created_at"])]

    def __str__(self) -> str:
        return f"{self.mission_id}:{self.author_id}"


class MissionEventAction(models.TextChoices):
    CREATED = "created", "创建"
    UPDATED = "updated", "修改"
    CLAIMED = "claimed", "认领"
    RELEASED = "released", "退出"
    SUBMITTED = "submitted", "提交成果"
    REVIEW_APPROVED = "review_approved", "验收通过"
    REVIEW_REJECTED = "review_rejected", "退回"
    CANCELLED = "cancelled", "取消"
    CHILD_CREATED = "child_created", "创建子任务"


class MissionEvent(models.Model):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mission_events",
    )
    action = models.CharField(max_length=32, choices=MissionEventAction.choices)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["mission", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.mission_id}:{self.action}"
