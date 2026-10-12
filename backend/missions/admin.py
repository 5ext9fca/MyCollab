from django.contrib import admin, messages

from . import services
from .exceptions import DomainError
from .models import (
    Comment,
    Milestone,
    Mission,
    MissionEvent,
    MissionStatus,
    MissionSubmission,
    Tag,
)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """Inspection only: comments are authored content, edited via services."""

    list_display = ["mission", "author", "created_at", "updated_at"]
    search_fields = ["content", "mission__title", "author__username"]
    readonly_fields = ["id", "mission", "author", "content", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MissionEventInline(admin.TabularInline):
    model = MissionEvent
    extra = 0
    can_delete = False
    ordering = ["-created_at"]
    readonly_fields = ["actor", "action", "payload", "created_at"]


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "due_date", "version", "created_by", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "description"]
    # Status changes go through services.transition_milestone.
    readonly_fields = ["id", "status", "version", "created_by", "created_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MissionSubmission)
class MissionSubmissionAdmin(admin.ModelAdmin):
    """Inspection only: submissions are immutable history."""

    list_display = ["mission", "outcome", "submitted_by", "submitted_at", "is_legacy"]
    list_filter = ["outcome", "is_legacy"]
    search_fields = ["description", "mission__title"]
    readonly_fields = [
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
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "type", "priority", "creator", "assignee", "parent", "version", "created_at"]
    list_filter = ["status", "type", "priority", "tags"]
    search_fields = ["title", "content", "acceptance_criteria"]
    filter_horizontal = ["tags"]
    inlines = [MissionEventInline]
    # Transition / assignment fields are read-only: state changes go through
    # services, not by editing fields directly (see TECH_STACK.md section 4).
    readonly_fields = [
        "id",
        "creator",
        "status",
        "type",
        "priority",
        "assignee",
        "reviewer",
        "milestone",
        "result",
        "current_submission",
        "version",
        "created_at",
        "updated_at",
    ]
    actions = [
        "action_claim",
        "action_release",
        "action_approve",
        "action_reject",
        "action_cancel",
    ]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
            obj.status = MissionStatus.OPEN
            obj.reviewer = request.user
        super().save_model(request, obj, form, change)

    def _run(self, request, queryset, func):
        ok = 0
        for mission in queryset:
            try:
                func(mission)
                ok += 1
            except DomainError as exc:
                self.message_user(
                    request, f"{mission.title}: {exc.message}", level=messages.ERROR
                )
        if ok:
            self.message_user(request, f"已成功处理 {ok} 个任务。", level=messages.SUCCESS)

    @admin.action(description="认领所选任务")
    def action_claim(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.claim_mission(
                actor=request.user, mission_id=m.id, expected_version=m.version
            ),
        )

    @admin.action(description="退出所选任务")
    def action_release(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.release_mission(
                actor=request.user, mission_id=m.id, expected_version=m.version
            ),
        )

    @admin.action(description="验收通过所选任务")
    def action_approve(self, request, queryset):
        def run(m):
            if m.current_submission_id is None:
                raise DomainError("没有待验收的提交。")
            services.review_mission(
                actor=request.user,
                mission_id=m.id,
                submission_id=m.current_submission_id,
                decision="accept",
                comment="管理员验收通过",
                expected_version=m.version,
            )

        self._run(request, queryset, run)

    @admin.action(description="退回所选任务")
    def action_reject(self, request, queryset):
        def run(m):
            if m.current_submission_id is None:
                raise DomainError("没有待验收的提交。")
            services.review_mission(
                actor=request.user,
                mission_id=m.id,
                submission_id=m.current_submission_id,
                decision="reject",
                comment="管理员退回",
                expected_version=m.version,
            )

        self._run(request, queryset, run)

    @admin.action(description="取消所选任务")
    def action_cancel(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.cancel_mission(
                actor=request.user,
                mission_id=m.id,
                reason="管理员取消",
                expected_version=m.version,
            ),
        )
