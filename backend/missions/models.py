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


class MissionType(models.TextChoices):
    """F1: a mission's kind. Reuses the same model, claim and state machine."""

    FEATURE = "Feature", "功能"
    TASK = "Task", "任务"
    BUG = "Bug", "缺陷"


class MissionPriority(models.TextChoices):
    """F2: fixed priority enum; ``P0`` is the most urgent."""

    P0 = "P0", "P0 紧急阻断"
    P1 = "P1", "P1 重要"
    P2 = "P2", "P2 普通"
    P3 = "P3", "P3 可延期"


class MilestoneStatus(models.TextChoices):
    PLANNED = "Planned", "计划中"
    ACTIVE = "Active", "进行中"
    COMPLETED = "Completed", "已完成"
    CANCELLED = "Cancelled", "已取消"


#: Statuses that require a non-null assignee.
ASSIGNEE_REQUIRED_STATUSES = [
    MissionStatus.IN_PROGRESS,
    MissionStatus.SUBMITTED,
    MissionStatus.DONE,
]

#: Statuses that still count as "active work" for milestone completion.
MILESTONE_OPEN_STATUSES = [
    MissionStatus.OPEN,
    MissionStatus.IN_PROGRESS,
    MissionStatus.SUBMITTED,
]

#: Milestone statuses that may receive new or reassigned missions.
MILESTONE_ACCEPTING_STATUSES = [MilestoneStatus.PLANNED, MilestoneStatus.ACTIVE]

#: Statuses during which dependencies may be added/removed.
EDITABLE_STATUSES = [MissionStatus.OPEN, MissionStatus.IN_PROGRESS]


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Milestone(models.Model):
    """F2: a scheduling bucket, not a parent mission and not a build version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=MilestoneStatus.choices,
        default=MilestoneStatus.PLANNED,
    )
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_milestones",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["due_date"]),
        ]

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
    type = models.CharField(max_length=16, choices=MissionType.choices, default=MissionType.TASK)
    priority = models.CharField(
        max_length=4, choices=MissionPriority.choices, default=MissionPriority.P2
    )
    # F3: reviewer defaults to the creator. It is nullable so that a reviewer who
    # left the team can be flagged (and cleared by an admin) without fabricating a
    # new reviewer; new submissions require an active reviewer.
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewing_missions",
        null=True,
        blank=True,
    )
    milestone = models.ForeignKey(
        Milestone,
        on_delete=models.PROTECT,
        related_name="missions",
        null=True,
        blank=True,
    )
    result = models.TextField(blank=True)
    current_submission = models.ForeignKey(
        "MissionSubmission",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
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
            models.Index(fields=["priority", "-created_at"]),
            models.Index(fields=["milestone", "status"]),
            models.Index(fields=["type", "status"]),
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


class MissionDependency(models.Model):
    """F1: ``mission`` waits for ``prerequisite`` before it can be completed.

    A dependency is a different relation from parent/child decomposition; the
    two must be modelled separately (see TECH_STACK.md section 5).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission,
        on_delete=models.CASCADE,
        related_name="dependencies",
    )
    prerequisite = models.ForeignKey(
        Mission,
        on_delete=models.CASCADE,
        related_name="dependents",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_dependencies",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["mission", "prerequisite"],
                name="dependency_unique_pair",
            ),
            models.CheckConstraint(
                condition=~Q(mission=models.F("prerequisite")),
                name="dependency_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["mission"]),
            models.Index(fields=["prerequisite"]),
        ]

    def __str__(self) -> str:
        return f"{self.mission_id} depends on {self.prerequisite_id}"


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


class SubmissionOutcome(models.TextChoices):
    PENDING = "Pending", "待验收"
    ACCEPTED = "Accepted", "已通过"
    REJECTED = "Rejected", "已退回"


class SubmissionProvider(models.TextChoices):
    """F4 source provider. Build references use free-form provider names."""

    GIT = "Git", "Git"
    PERFORCE = "Perforce", "Perforce"
    UVCS = "UVCS", "Unity Version Control"
    OTHER = "Other", "其他"


class BuildStatus(models.TextChoices):
    UNKNOWN = "Unknown", "未知"
    PENDING = "Pending", "等待中"
    SUCCEEDED = "Succeeded", "成功"
    FAILED = "Failed", "失败"


class MissionSubmission(models.Model):
    """F3/F4: one immutable round of deliverables.

    Every submit creates a new row; rejecting/resubmitting never overwrites an
    older round. ``is_legacy`` marks rows imported from pre-submission data and
    cannot be set by clients.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="submissions")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mission_submissions",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)
    verification_description = models.TextField(blank=True)
    is_legacy = models.BooleanField(default=False)
    reviewer_snapshot = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="snapshot_submissions",
        null=True,
        blank=True,
    )
    outcome = models.CharField(
        max_length=16,
        choices=SubmissionOutcome.choices,
        default=SubmissionOutcome.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_submissions",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    verified_build_reference = models.ForeignKey(
        "SubmissionBuildReference",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["mission", "-submitted_at"]),
            models.Index(fields=["outcome"]),
        ]

    def __str__(self) -> str:
        return f"{self.mission_id}:{self.outcome}"


class SubmissionSourceReference(models.Model):
    """F4: a VCS commit / changelist referenced by a submission. Immutable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        MissionSubmission, on_delete=models.CASCADE, related_name="source_references"
    )
    provider = models.CharField(
        max_length=16, choices=SubmissionProvider.choices, default=SubmissionProvider.GIT
    )
    repository = models.CharField(max_length=300)
    revision = models.CharField(max_length=200)
    browse_url = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.repository}@{self.revision}"


class SubmissionBuildReference(models.Model):
    """F4: a game build referenced by a submission. Immutable.

    ``status`` is the build result, not the QA/review result; a successful build
    never moves a mission to Done by itself.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        MissionSubmission, on_delete=models.CASCADE, related_name="build_references"
    )
    provider = models.CharField(max_length=50)
    build_id = models.CharField(max_length=100)
    platform = models.CharField(max_length=50)
    source_revision = models.CharField(max_length=200, blank=True)
    artifact_url = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=16, choices=BuildStatus.choices, default=BuildStatus.UNKNOWN
    )
    verification_note = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.build_id} ({self.platform})"


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
    TYPE_CHANGED = "type_changed", "修改类型"
    PRIORITY_CHANGED = "priority_changed", "修改优先级"
    REVIEWER_CHANGED = "reviewer_changed", "修改验收者"
    REVIEW_TRANSFERRED = "review_transferred", "转交验收"
    REOPENED = "reopened", "重新打开"
    MILESTONE_CHANGED = "milestone_changed", "修改里程碑"
    DEPENDENCY_ADDED = "dependency_added", "添加依赖"
    DEPENDENCY_REMOVED = "dependency_removed", "移除依赖"


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


class MilestoneEventAction(models.TextChoices):
    CREATED = "created", "创建"
    UPDATED = "updated", "修改"
    TRANSITIONED = "transitioned", "变更状态"


class MilestoneEvent(models.Model):
    """Milestone-scoped activity log (milestones are not missions)."""

    milestone = models.ForeignKey(
        Milestone, on_delete=models.CASCADE, related_name="events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="milestone_events",
    )
    action = models.CharField(max_length=32, choices=MilestoneEventAction.choices)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["milestone", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.milestone_id}:{self.action}"
