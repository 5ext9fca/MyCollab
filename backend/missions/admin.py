from django.contrib import admin, messages

from . import services
from .exceptions import DomainError
from .models import Comment, Mission, MissionEvent, MissionStatus, Tag


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


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "creator", "assignee", "parent", "version", "created_at"]
    list_filter = ["status", "tags"]
    search_fields = ["title", "content", "acceptance_criteria"]
    filter_horizontal = ["tags"]
    inlines = [MissionEventInline]
    # Transition fields are read-only: state changes go through services, not by
    # editing fields directly (see TECH_STACK.md section 4).
    readonly_fields = [
        "id",
        "creator",
        "status",
        "assignee",
        "result",
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
            lambda m: services.claim_mission(actor=request.user, mission_id=m.id),
        )

    @admin.action(description="退出所选任务")
    def action_release(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.release_mission(actor=request.user, mission_id=m.id),
        )

    @admin.action(description="验收通过所选任务")
    def action_approve(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.review_mission(
                actor=request.user, mission_id=m.id, approve=True
            ),
        )

    @admin.action(description="退回所选任务")
    def action_reject(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.review_mission(
                actor=request.user, mission_id=m.id, approve=False
            ),
        )

    @admin.action(description="取消所选任务")
    def action_cancel(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda m: services.cancel_mission(
                actor=request.user, mission_id=m.id, reason="管理员取消"
            ),
        )
