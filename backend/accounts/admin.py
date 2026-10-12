from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from common.exceptions import DomainError

from . import services
from .models import RegistrationRequest, RegistrationStatus, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    pass


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ["username", "email", "status", "created_at", "reviewed_by", "reviewed_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["username", "email", "display_name"]
    # Approval is a state transition and goes through services, not field edits.
    readonly_fields = [
        "id",
        "username",
        "email",
        "display_name",
        "password_hash",
        "message",
        "status",
        "review_note",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    ]
    actions = ["action_approve", "action_reject"]

    def _run(self, request, queryset, func):
        ok = 0
        for registration in queryset:
            try:
                func(registration)
                ok += 1
            except DomainError as exc:
                self.message_user(
                    request, f"{registration.username}: {exc.message}", level=messages.ERROR
                )
        if ok:
            self.message_user(request, f"已处理 {ok} 个注册申请。", level=messages.SUCCESS)

    @admin.action(description="通过所选注册申请")
    def action_approve(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda r: services.approve_registration(actor=request.user, request_id=r.id),
        )

    @admin.action(description="拒绝所选注册申请")
    def action_reject(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda r: services.reject_registration(
                actor=request.user, request_id=r.id, note="管理员拒绝"
            ),
        )
