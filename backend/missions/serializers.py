from rest_framework import serializers
from django.utils import timezone

from accounts.serializers import UserBriefSerializer

from .models import (
    BuildStatus,
    Comment,
    Milestone,
    MilestoneEvent,
    Mission,
    MissionEvent,
    MissionPriority,
    MissionSubmission,
    MissionType,
    SubmissionBuildReference,
    SubmissionProvider,
    SubmissionSourceReference,
    Tag,
)
from .services import allowed_actions, derived_state, milestone_progress


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]


class MilestoneBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ["id", "name", "status", "due_date"]


class MissionRefSerializer(serializers.ModelSerializer):
    """Lightweight mission reference used by dependency lists."""

    class Meta:
        model = Mission
        fields = ["id", "title", "status", "type", "priority"]


class MissionListSerializer(serializers.ModelSerializer):
    creator = UserBriefSerializer(read_only=True)
    assignee = UserBriefSerializer(read_only=True)
    reviewer = UserBriefSerializer(read_only=True)
    parent = serializers.UUIDField(source="parent_id", read_only=True, allow_null=True)
    milestone = MilestoneBriefSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    # F1/F3 derived flags (never stored).
    has_unresolved_prerequisites = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    blocking_mission_ids = serializers.SerializerMethodField()
    unfinished_child_ids = serializers.SerializerMethodField()
    needs_dependency_review = serializers.SerializerMethodField()
    reviewer_missing = serializers.SerializerMethodField()
    milestone_closed = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        fields = [
            "id",
            "title",
            "status",
            "type",
            "priority",
            "creator",
            "assignee",
            "reviewer",
            "parent",
            "milestone",
            "tags",
            "version",
            "created_at",
            "updated_at",
            "allowed_actions",
            "has_unresolved_prerequisites",
            "is_blocked",
            "blocking_mission_ids",
            "unfinished_child_ids",
            "needs_dependency_review",
            "reviewer_missing",
            "milestone_closed",
        ]

    def _derived(self, obj):
        cache = getattr(obj, "_derived_cache", None)
        if cache is None:
            cache = derived_state(obj)
            obj._derived_cache = cache
        return cache

    def get_allowed_actions(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return allowed_actions(user, obj)

    def get_has_unresolved_prerequisites(self, obj):
        return self._derived(obj)["has_unresolved_prerequisites"]

    def get_is_blocked(self, obj):
        return self._derived(obj)["is_blocked"]

    def get_blocking_mission_ids(self, obj):
        return self._derived(obj)["blocking_mission_ids"]

    def get_unfinished_child_ids(self, obj):
        return self._derived(obj)["unfinished_child_ids"]

    def get_needs_dependency_review(self, obj):
        return self._derived(obj)["needs_dependency_review"]

    def get_reviewer_missing(self, obj):
        return self._derived(obj)["reviewer_missing"]

    def get_milestone_closed(self, obj):
        return self._derived(obj)["milestone_closed"]


class MissionDetailSerializer(MissionListSerializer):
    children = serializers.SerializerMethodField()
    prerequisites = serializers.SerializerMethodField()
    dependents = serializers.SerializerMethodField()
    current_submission = serializers.UUIDField(source="current_submission_id", read_only=True)

    class Meta(MissionListSerializer.Meta):
        fields = MissionListSerializer.Meta.fields + [
            "content",
            "acceptance_criteria",
            "result",
            "children",
            "prerequisites",
            "dependents",
            "current_submission",
        ]

    def get_children(self, obj):
        children = obj.children.select_related("creator", "assignee", "reviewer", "milestone").order_by(
            "created_at"
        )
        return MissionListSerializer(children, many=True, context=self.context).data

    def get_prerequisites(self, obj):
        prerequisites = Mission.objects.filter(dependents__mission_id=obj.id).order_by("created_at")
        return MissionRefSerializer(prerequisites, many=True).data

    def get_dependents(self, obj):
        dependents = Mission.objects.filter(dependencies__prerequisite_id=obj.id).order_by("created_at")
        return MissionRefSerializer(dependents, many=True).data


class MissionEventSerializer(serializers.ModelSerializer):
    actor = UserBriefSerializer(read_only=True)

    class Meta:
        model = MissionEvent
        fields = ["id", "actor", "action", "payload", "created_at"]


class MilestoneEventSerializer(serializers.ModelSerializer):
    actor = UserBriefSerializer(read_only=True)

    class Meta:
        model = MilestoneEvent
        fields = ["id", "actor", "action", "payload", "created_at"]


class MissionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(required=False, allow_blank=True, default="")
    acceptance_criteria = serializers.CharField(required=False, allow_blank=True, default="")
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, default=list
    )
    parent = serializers.UUIDField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=MissionType.choices, required=False, default=MissionType.TASK)
    priority = serializers.ChoiceField(
        choices=MissionPriority.choices, required=False, default=MissionPriority.P2
    )
    reviewer_id = serializers.IntegerField(required=False, allow_null=True)
    milestone_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("标题不能为空。")
        return value


class MissionUpdateSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField()
    title = serializers.CharField(max_length=200, required=False)
    content = serializers.CharField(required=False, allow_blank=True)
    acceptance_criteria = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=50), required=False)
    parent = serializers.UUIDField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=MissionType.choices, required=False)
    priority = serializers.ChoiceField(choices=MissionPriority.choices, required=False)
    reviewer = serializers.IntegerField(required=False, allow_null=True)
    milestone = serializers.UUIDField(required=False, allow_null=True)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("标题不能为空。")
        return value


class SourceReferenceSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SubmissionProvider.choices, required=False, default=SubmissionProvider.GIT)
    repository = serializers.CharField(max_length=300)
    revision = serializers.CharField(max_length=200)
    browse_url = serializers.CharField(required=False, allow_blank=True, default="")


class BuildReferenceSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=50)
    build_id = serializers.CharField(max_length=100)
    platform = serializers.CharField(max_length=50)
    source_revision = serializers.CharField(required=False, allow_blank=True, default="")
    artifact_url = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=BuildStatus.choices, required=False, default=BuildStatus.UNKNOWN)
    verification_note = serializers.CharField(required=False, allow_blank=True, default="")


class SubmitSerializer(serializers.Serializer):
    # ``result`` is accepted as a backward-compatible alias for ``description``.
    description = serializers.CharField(required=False, allow_blank=True, default="")
    result = serializers.CharField(required=False, allow_blank=True, default="")
    verification_description = serializers.CharField(required=False, allow_blank=True, default="")
    source_references = SourceReferenceSerializer(many=True, required=False, default=list)
    build_references = BuildReferenceSerializer(many=True, required=False, default=list)
    expected_version = serializers.IntegerField()

    def validate(self, attrs):
        if not attrs.get("description") and attrs.get("result"):
            attrs["description"] = attrs.pop("result")
        return attrs


class ReviewSerializer(serializers.Serializer):
    submission_id = serializers.UUIDField()
    decision = serializers.CharField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    verified_build_reference_id = serializers.UUIDField(required=False, allow_null=True)
    expected_version = serializers.IntegerField()


class TransferReviewSerializer(serializers.Serializer):
    new_reviewer_id = serializers.IntegerField()
    reason = serializers.CharField()
    expected_version = serializers.IntegerField()


class ReopenSerializer(serializers.Serializer):
    reason = serializers.CharField()
    expected_version = serializers.IntegerField()


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    expected_version = serializers.IntegerField()


class ClaimSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField()


class DependencyCreateSerializer(serializers.Serializer):
    prerequisite_id = serializers.UUIDField()
    expected_version = serializers.IntegerField()


class SubmissionSourceReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionSourceReference
        fields = ["id", "provider", "repository", "revision", "browse_url"]


class SubmissionBuildReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionBuildReference
        fields = [
            "id",
            "provider",
            "build_id",
            "platform",
            "source_revision",
            "artifact_url",
            "status",
            "verification_note",
        ]


class MissionSubmissionSerializer(serializers.ModelSerializer):
    submitted_by = UserBriefSerializer(read_only=True)
    reviewer_snapshot = UserBriefSerializer(read_only=True)
    reviewed_by = UserBriefSerializer(read_only=True)
    source_references = SubmissionSourceReferenceSerializer(many=True, read_only=True)
    build_references = SubmissionBuildReferenceSerializer(many=True, read_only=True)

    class Meta:
        model = MissionSubmission
        fields = [
            "id",
            "mission",
            "submitted_by",
            "submitted_at",
            "description",
            "verification_description",
            "is_legacy",
            "reviewer_snapshot",
            "outcome",
            "reviewed_by",
            "reviewed_at",
            "review_comment",
            "verified_build_reference",
            "source_references",
            "build_references",
        ]


class MilestoneSerializer(serializers.ModelSerializer):
    created_by = UserBriefSerializer(read_only=True)
    progress = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    mission_counts = serializers.SerializerMethodField()

    class Meta:
        model = Milestone
        fields = [
            "id",
            "name",
            "description",
            "due_date",
            "status",
            "version",
            "created_by",
            "created_at",
            "updated_at",
            "progress",
            "overdue",
            "mission_counts",
        ]

    def get_progress(self, obj):
        return milestone_progress(obj)["progress"]

    def get_overdue(self, obj):
        if obj.due_date is None or obj.status not in ("Planned", "Active"):
            return False
        return obj.due_date < timezone.localdate()

    def get_mission_counts(self, obj):
        return milestone_progress(obj)


class MilestoneCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    due_date = serializers.DateField(required=False, allow_null=True)


class MilestoneUpdateSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField()
    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)


class MilestoneTransitionSerializer(serializers.Serializer):
    status = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    expected_version = serializers.IntegerField()


class CommentSerializer(serializers.ModelSerializer):
    """Read model for a mission comment (Markdown content, like Mission.content)."""

    author = UserBriefSerializer(read_only=True)
    mission = serializers.UUIDField(source="mission_id", read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "mission",
            "author",
            "content",
            "created_at",
            "updated_at",
            "can_edit",
        ]

    def get_can_edit(self, obj: Comment) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and obj.author_id == user.pk)


class CommentCreateSerializer(serializers.Serializer):
    # Mirrors Mission.content: Markdown text, blank allowed.
    content = serializers.CharField(required=False, allow_blank=True, default="")


class CommentUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(required=True, allow_blank=True)
