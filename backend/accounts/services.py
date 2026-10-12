"""Single business entry point for user registration and approval.

Views (public registration and the admin console API) and Django Admin actions
all call these functions, so the approval rules cannot be bypassed by editing
fields directly. Approval uses a row lock plus a status guard, mirroring the
Mission state machine: two admins approving the same request at once leave
exactly one winner, the other gets ``409 registration_already_reviewed``.
"""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.exceptions import ConflictError, NotFound, ValidationFailure

from .models import RegistrationRequest, RegistrationStatus, User

PENDING = RegistrationStatus.PENDING


def _get_locked(request_id) -> RegistrationRequest:
    try:
        return RegistrationRequest.objects.select_for_update().get(pk=request_id)
    except RegistrationRequest.DoesNotExist:
        raise NotFound("注册申请不存在。")


@transaction.atomic
def submit_registration(
    *,
    username: str,
    password: str,
    email: str = "",
    display_name: str = "",
    message: str = "",
) -> RegistrationRequest:
    """Create a pending registration request; never touches ``auth_user``."""
    username = (username or "").strip()
    if not username:
        raise ValidationFailure(
            "用户名不能为空。", field_errors={"username": ["用户名不能为空。"]}
        )
    if not password:
        raise ValidationFailure(
            "密码不能为空。", field_errors={"password": ["密码不能为空。"]}
        )
    if User.objects.filter(username__iexact=username).exists():
        raise ConflictError(
            "用户名已被占用。",
            code="username_taken",
            field_errors={"username": ["用户名已被占用。"]},
        )
    if RegistrationRequest.objects.filter(username__iexact=username, status=PENDING).exists():
        raise ConflictError(
            "该用户名已有待审批的注册申请。",
            code="registration_pending",
            field_errors={"username": ["已有待审批的注册申请。"]},
        )
    return RegistrationRequest.objects.create(
        username=username,
        email=(email or "").strip(),
        display_name=(display_name or "").strip(),
        password_hash=make_password(password),
        message=(message or "").strip(),
    )


@transaction.atomic
def approve_registration(*, actor, request_id) -> RegistrationRequest:
    """Turn a pending request into an active user account."""
    registration = _get_locked(request_id)
    if registration.status != PENDING:
        raise ConflictError(
            "该申请已处理。",
            code="registration_already_reviewed",
            field_errors={"status": ["该申请已处理。"]},
        )
    if User.objects.filter(username__iexact=registration.username).exists():
        raise ConflictError(
            "用户名已被占用，无法通过。",
            code="username_taken",
            field_errors={"username": ["用户名已被占用。"]},
        )

    user = User(
        username=registration.username,
        email=registration.email,
        first_name=registration.display_name,
        is_active=True,
    )
    user.password = registration.password_hash
    try:
        user.save()
    except IntegrityError:
        raise ConflictError(
            "用户名已被占用，无法通过。",
            code="username_taken",
            field_errors={"username": ["用户名已被占用。"]},
        )

    registration.status = RegistrationStatus.APPROVED
    registration.reviewed_by = actor
    registration.reviewed_at = timezone.now()
    registration.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return registration


@transaction.atomic
def reject_registration(*, actor, request_id, note: str = "") -> RegistrationRequest:
    """Reject a pending request; no user account is created."""
    registration = _get_locked(request_id)
    if registration.status != PENDING:
        raise ConflictError(
            "该申请已处理。",
            code="registration_already_reviewed",
            field_errors={"status": ["该申请已处理。"]},
        )
    registration.status = RegistrationStatus.REJECTED
    registration.review_note = (note or "").strip()
    registration.reviewed_by = actor
    registration.reviewed_at = timezone.now()
    registration.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at"])
    return registration
