"""短期文件直传会话；不接收或保存文件内容。"""
import hashlib
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from common.exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from .models import FileTransfer

MAX_BYTES = 100 * 1024 * 1024
TERMINAL = {"completed", "failed", "cancelled", "expired"}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def validate_token(token):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValidationFailure("会话凭据无效。")


def member(actor):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied()


def capacity(actor):
    User.objects.select_for_update().get(pk=actor.pk)
    now = timezone.now()
    active = FileTransfer.objects.filter(Q(sender=actor) | Q(receiver=actor), expires_at__gt=now).exclude(status__in=TERMINAL).exclude(status__in=["waiting", "paired"], pair_expires_at__lte=now)
    if active.count() >= 3:
        raise ConflictError("最多同时进行 3 个传输会话，请取消旧会话或等待过期。")


def expire(record):
    now = timezone.now()
    if record.status not in TERMINAL and (record.expires_at <= now or (record.status in {"waiting", "paired"} and record.pair_expires_at <= now)):
        finish(record, "expired")


def finish(record, status, error=""):
    record.status = status
    record.error = error
    record.offer = record.answer = ""
    record.save()


def snapshot(record, role):
    return {
        "id": str(record.id), "role": role, "name": record.name, "size": record.size,
        "sha256": record.sha256, "received_sha256": record.received_sha256,
        "status": record.status, "error": record.error,
        "sender_name": (record.sender.get_full_name() or record.sender.get_username()), "receiver_name": (record.receiver.get_full_name() or record.receiver.get_username()) if record.receiver else None,
        "pair_expires_at": record.pair_expires_at.isoformat(), "expires_at": record.expires_at.isoformat(),
        "offer": record.offer if role == "receiver" else "",
        "answer": record.answer if role == "sender" else "",
    }


@transaction.atomic
def create_transfer(*, actor, name, size, sha256, token):
    member(actor)
    validate_token(token)
    if not isinstance(name, str) or not name.strip() or len(name) > 255 or any(ord(c) < 32 or c in "/\\" for c in name):
        raise ValidationFailure("文件名无效。")
    if type(size) is not int or not 0 <= size <= MAX_BYTES:
        raise ValidationFailure("单文件不得超过 100 MiB。")
    if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValidationFailure("必须提供 SHA-256 校验值。")
    capacity(actor)
    code = secrets.token_hex(6).upper()
    now = timezone.now()
    record = FileTransfer.objects.create(sender=actor, sender_token=digest(token), code_digest=digest(code), name=name, size=size, sha256=sha256, pair_expires_at=now + timedelta(minutes=5), expires_at=now + timedelta(minutes=30))
    return {**snapshot(record, "sender"), "code": code}


@transaction.atomic
def join_transfer(*, actor, code, token):
    member(actor)
    validate_token(token)
    if not isinstance(code, str) or not re.fullmatch(r"[A-Fa-f0-9]{12}", code):
        raise ValidationFailure("请输入 12 位配对码。")
    User.objects.select_for_update().get(pk=actor.pk)
    record = FileTransfer.objects.select_for_update().filter(code_digest=digest(code.upper())).first()
    if not record:
        raise NotFound("配对码不存在或已失效。")
    expire(record)
    if record.status == "paired" and record.receiver_id == actor.pk and secrets.compare_digest(record.receiver_token, digest(token)):
        return snapshot(record, "receiver")
    if record.status != "waiting":
        raise ConflictError("配对码已使用或已失效。")
    capacity(actor)
    if secrets.compare_digest(record.sender_token, digest(token)):
        raise ConflictError("请在另一个页面接收文件。")
    record.receiver = actor
    record.receiver_token = digest(token)
    record.status = "paired"
    record.save()
    return snapshot(record, "receiver")


@transaction.atomic
def operate_transfer(*, actor, transfer_id, token, action="poll", sdp="", sha256="", error=""):
    member(actor)
    validate_token(token)
    record = FileTransfer.objects.select_for_update().filter(pk=transfer_id).first()
    if not record:
        raise NotFound("传输会话不存在或已清理。")
    hashed = digest(token)
    if record.sender_id == actor.pk and secrets.compare_digest(record.sender_token, hashed):
        role = "sender"
    elif record.receiver_id == actor.pk and secrets.compare_digest(record.receiver_token, hashed):
        role = "receiver"
    else:
        raise PermissionDenied("无权访问此传输会话。")
    if not record.sender.is_active or (record.receiver and not record.receiver.is_active):
        finish(record, "cancelled")
    expire(record)
    if action == "poll":
        return snapshot(record, role)
    if action not in {"accept", "offer", "answer", "complete", "cancel", "fail"}:
        raise ValidationFailure("未知传输操作。")
    if record.status in TERMINAL:
        return snapshot(record, role)
    if action == "cancel":
        finish(record, "cancelled")
    elif action == "fail":
        if error not in {"connection_failed", "checksum_mismatch", "protocol_error", "timeout", "local_error"}:
            raise ValidationFailure("无效错误码。")
        finish(record, "failed", error)
    elif action == "accept":
        if role != "receiver" or record.status not in {"paired", "accepted"}:
            raise ConflictError("当前无法接受传输。")
        record.status = "accepted"
        record.save(update_fields=["status"])
    elif action in {"offer", "answer"}:
        if record.status != "accepted" or role != ("sender" if action == "offer" else "receiver"):
            raise ConflictError("当前无法交换连接信息。")
        if not isinstance(sdp, str) or not sdp.startswith("v=0") or len(sdp) > 16384 or "m=application " not in sdp or "m=audio " in sdp or "m=video " in sdp:
            raise ValidationFailure("连接信息无效或过大。")
        if action == "answer" and not record.offer:
            raise ConflictError("发送端尚未准备好连接。")
        previous = getattr(record, action)
        if previous and previous != sdp:
            raise ConflictError("连接信息不能覆盖，请重新创建传输。")
        setattr(record, action, sdp)
        record.save(update_fields=[action])
    elif action == "complete":
        if role != "receiver" or record.status != "accepted" or not record.answer:
            raise ConflictError("当前无法确认校验结果。")
        if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise ValidationFailure("必须提供接收端 SHA-256。")
        record.received_sha256 = sha256
        finish(record, "completed" if secrets.compare_digest(record.sha256, sha256) else "failed", "" if sha256 == record.sha256 else "checksum_mismatch")
    return snapshot(record, role)


def cleanup_transfers():
    return FileTransfer.objects.filter(expires_at__lte=timezone.now()).delete()[0]
