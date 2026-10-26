"""只管理本地辅助交接，不写入任何 Mission、设计或模板。"""

import hashlib
import json
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from library.references import assert_markdown_references_allowed
from missions.models import Comment, DesignElement, Mission, ProductionTemplate
from missions.services import allowed_actions, design_allowed_actions, template_allowed_actions, _validate_template_steps

from .models import AgentDevice, AssistanceRequest
from . import protocol

ACTIVE = ("queued", "running")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def validate(call, *args):
    try:
        return call(*args)
    except protocol.ProtocolError as exc:
        raise ValidationFailure(str(exc)) from exc


def active_user(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("仅有效成员可以使用本地辅助。")


def device_available(device):
    active_user(device.owner)
    if device.revoked_at or device.expires_at <= timezone.now():
        raise PermissionDenied("设备已撤销或凭据已过期。")


@transaction.atomic
def create_device(actor, *, name, capabilities, expires_days=30):
    active_user(actor)
    active_user(get_user_model().objects.select_for_update().get(pk=actor.pk))
    validate(protocol.text, name, 100, True)
    if not isinstance(capabilities, list) or not capabilities or any(c not in protocol.KINDS for c in capabilities):
        raise ValidationFailure("请选择支持的文本辅助能力。")
    if type(expires_days) is not int or not 1 <= expires_days <= 90:
        raise ValidationFailure("有效期须为 1–90 天。")
    if AgentDevice.objects.filter(owner=actor, revoked_at=None, expires_at__gt=timezone.now()).count() >= 10:
        raise ValidationFailure("最多保留 10 台有效设备，请先撤销闲置设备。")
    token = "mc_agent_" + secrets.token_urlsafe(32)
    device = AgentDevice.objects.create(owner=actor, name=name.strip(), capabilities=list(dict.fromkeys(capabilities)),
        token_digest=digest(token), expires_at=timezone.now() + timedelta(days=expires_days))
    return device, token


@transaction.atomic
def revoke_device(actor, device_id):
    device = AgentDevice.objects.select_for_update().filter(pk=device_id, owner=actor).first()
    if not device:
        raise NotFound()
    if not device.revoked_at:
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])
        device.requests.filter(status="queued").update(status="cancelled", stopped_at=timezone.now(), updated_at=timezone.now())
        device.requests.filter(status="running").update(status="cancelled", updated_at=timezone.now())
    return device


def expire_requests(queryset):
    now = timezone.now()
    queryset.filter(status__in=ACTIVE).filter(
        Q(expires_at__lte=now) | Q(status="running", lease_expires_at__lte=now)
    ).update(status="expired", updated_at=now)


def check_target(actor, kind, object_id, base_version, submission_id):
    active_user(actor)
    if kind == "agent_requirements":
        if object_id is None or submission_id is not None:
            raise ValidationFailure("导出需要已有 Mission，不能携带提交轮次。")
        obj = Mission.objects.filter(pk=object_id).first()
        if not obj:
            raise NotFound("Mission 不存在。")
        if type(base_version) is not int or obj.version != base_version:
            raise ConflictError("Mission 版本已变化，请刷新后重新导出。", code="version_conflict")
        return obj
    if object_id is None:
        if base_version is not None or submission_id is not None or kind == "review_assist":
            raise ValidationFailure("验收需要任务与提交轮次，新建草稿不能携带版本。")
        return None
    model, actions = {
        "design_polish": (DesignElement, design_allowed_actions),
        "template_generate": (ProductionTemplate, template_allowed_actions),
        "mission_write": (Mission, allowed_actions),
        "review_assist": (Mission, allowed_actions),
    }[kind]
    obj = model.objects.filter(pk=object_id).first()
    if not obj:
        raise NotFound("关联对象已不存在。")
    required = "review" if kind == "review_assist" else "edit"
    if required not in actions(actor, obj):
        raise PermissionDenied("当前对象不允许此辅助操作。")
    if type(base_version) is not int or obj.version != base_version:
        raise ConflictError("对象版本已变化，请重新加载并比较。", code="version_conflict")
    if kind == "review_assist":
        submission = obj.current_submission
        if not submission or str(submission.pk) != str(submission_id) or submission.outcome != "Pending":
            raise ConflictError("待验收轮次已变化，请重新分析。", code="submission_conflict")
    elif submission_id is not None:
        raise ValidationFailure("只有验收辅助可携带提交轮次。")
    return obj


def build_input(actor, kind, draft, instructions, context_ids, parent_id, obj, submission_id, comment_ids):
    validate(protocol.text, instructions, 10000)
    if kind == "agent_requirements":
        from .requirements import snapshot
        validate(protocol.fields, draft, ())
        if instructions or context_ids or parent_id or comment_ids:
            raise ValidationFailure("需求文档只使用服务器当前 Mission 及其关联设计、资产。")
        return snapshot(obj)
    if not isinstance(context_ids, list) or len(context_ids) > 20 or len(set(context_ids)) != len(context_ids):
        raise ValidationFailure("最多选择 20 项不重复的设计/资产上下文。")
    contexts = []
    for context_id in context_ids:
        item = DesignElement.objects.filter(pk=context_id, archived=False).first()
        if not item:
            raise ValidationFailure("选择的设计/资产不存在或已归档。")
        contexts.append({"id": str(item.pk), "version": item.version, "kind": item.kind, "title": item.title, "content": item.content})
    if kind == "review_assist":
        validate(protocol.fields, draft, ())
        submission = obj.submissions.get(pk=submission_id)
        draft = {"title": obj.title, "content": obj.content, "acceptance_criteria": obj.acceptance_criteria,
            "submission_id": str(submission.pk), "description": submission.description,
            "verification_description": submission.verification_description,
            "source_references": list(submission.source_references.values("provider", "repository", "revision", "browse_url")),
            "build_references": list(submission.build_references.values("provider", "build_id", "platform", "source_revision", "artifact_url", "status", "verification_note"))}
    else:
        allowed = {
            "design_polish": ("title", "content", "kind"),
            "template_generate": ("name", "description", "steps"),
            "mission_write": ("title", "content", "acceptance_criteria", "type", "priority", "tags"),
        }[kind]
        validate(protocol.fields, draft, allowed)
        for key, value in draft.items():
            if key not in ("steps", "tags"):
                validate(protocol.text, value)
        if kind == "design_polish" and draft["kind"] not in ("Design", "Asset"):
            raise ValidationFailure("条目类型无效。")
        if kind == "mission_write":
            validate(protocol.strings, draft["tags"], 30, 50)
            if draft["type"] not in ("Feature", "Task", "Bug") or draft["priority"] not in ("P0", "P1", "P2", "P3"):
                raise ValidationFailure("类型或优先级无效。")
        if kind == "template_generate":
            if not isinstance(draft["steps"], list) or len(draft["steps"]) > 30:
                raise ValidationFailure("模板草稿最多包含 30 个步骤。")
            for step in draft["steps"]:
                validate(protocol.fields, step, ("key", "title", "content", "acceptance_criteria", "type", "priority", "tags", "prerequisite_keys"))
                for field in ("key", "title", "content", "acceptance_criteria", "type", "priority"):
                    validate(protocol.text, step[field])
                validate(protocol.strings, step["tags"], 30, 50)
                validate(protocol.strings, step["prerequisite_keys"], 30, 50)
    parent = None
    if parent_id:
        if kind != "mission_write":
            raise ValidationFailure("只有 Mission 编写允许父任务上下文。")
        item = Mission.objects.filter(pk=parent_id).first()
        if not item or "create_child" not in allowed_actions(actor, item):
            raise PermissionDenied("当前父任务不可创建子任务。")
        parent = {"id": str(item.pk), "version": item.version, "title": item.title, "content": item.content, "acceptance_criteria": item.acceptance_criteria}
    comments = []
    if comment_ids:
        if kind != "review_assist" or not obj or len(comment_ids) > 20 or len(set(comment_ids)) != len(comment_ids):
            raise ValidationFailure("验收辅助最多选择本任务的 20 条评论。")
        for comment_id in comment_ids:
            comment = Comment.objects.filter(pk=comment_id, mission=obj).first()
            if not comment:
                raise ValidationFailure("所选评论不属于当前任务或已删除。")
            comments.append({"id": str(comment.pk), "content": comment.content, "updated_at": comment.updated_at.isoformat()})
    result = {"draft": draft, "instructions": instructions, "contexts": contexts, "parent": parent, "comments": comments}
    validate(protocol.bounded_json, result, protocol.INPUT_LIMIT)
    return result


@transaction.atomic
def create_request(actor, *, device_id, kind, idempotency_key, draft, instructions="", context_ids=None,
                   object_id=None, base_version=None, submission_id=None, parent_id=None, retry_of=None, comment_ids=None):
    active_user(actor)
    # 同一用户的配额与幂等键检查串行；不在事务内调用模型。
    active_user(get_user_model().objects.select_for_update().get(pk=actor.pk))
    if kind not in protocol.KINDS:
        raise ValidationFailure("不支持的辅助类型。")
    payload = dict(device_id=str(device_id), kind=kind, draft=draft, instructions=instructions,
        context_ids=[str(i) for i in (context_ids or [])], object_id=str(object_id) if object_id else None,
        base_version=base_version, submission_id=str(submission_id) if submission_id else None,
        parent_id=str(parent_id) if parent_id else None, retry_of=str(retry_of) if retry_of else None,
        comment_ids=[str(i) for i in (comment_ids or [])])
    validate(protocol.bounded_json, payload, protocol.INPUT_LIMIT)
    fingerprint = digest(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    previous = AssistanceRequest.objects.filter(owner=actor, idempotency_key=idempotency_key).first()
    if previous:
        if previous.payload_digest != fingerprint:
            raise ConflictError("幂等键已用于另一份请求。", code="idempotency_conflict")
        return previous
    device = AgentDevice.objects.select_for_update().filter(pk=device_id, owner=actor).first()
    if not device:
        raise NotFound("设备不存在。")
    device_available(device)
    if kind not in device.capabilities:
        raise ValidationFailure("设备未声明此能力。")
    expire_requests(AssistanceRequest.objects.filter(owner=actor))
    if AssistanceRequest.objects.filter(owner=actor, status__in=ACTIVE).count() >= 3:
        raise ConflictError("最多同时保留 3 个活动请求。", code="request_limit")
    prior = None
    if retry_of:
        prior = AssistanceRequest.objects.filter(pk=retry_of, owner=actor, kind=kind).first()
        if not prior or prior.status in ACTIVE:
            raise ValidationFailure("只能明确重试本人的已结束请求。")
    obj = check_target(actor, kind, object_id, base_version, submission_id)
    snapshot = build_input(actor, kind, draft, instructions, context_ids or [], parent_id, obj, submission_id, comment_ids or [])
    return AssistanceRequest.objects.create(owner=actor, device=device, kind=kind, object_id=object_id,
        base_version=base_version, submission_id=submission_id, input=snapshot,
        idempotency_key=idempotency_key, payload_digest=fingerprint, retry_of=prior,
        expires_at=timezone.now() + timedelta(minutes=15))


def stale_reason(request):
    from common.exceptions import DomainError
    try:
        obj = check_target(request.owner, request.kind, request.object_id, request.base_version, request.submission_id)
        if request.kind == "agent_requirements":
            from .requirements import snapshot
            if snapshot(obj) != request.input:
                raise ConflictError("Mission 或关联设计、资产已变化，请重新导出。")
            return ""
        for comment in request.input.get("comments", []):
            if not Comment.objects.filter(pk=comment["id"], mission_id=request.object_id, updated_at=comment["updated_at"]).exists():
                raise ConflictError("所选评论已变化，请重新分析。")
        for context in request.input.get("contexts", []):
            if not DesignElement.objects.filter(pk=context["id"], archived=False, version=context["version"]).exists():
                raise ConflictError("所选上下文已变化，请重新预览并请求。")
        parent = request.input.get("parent")
        if parent:
            obj = Mission.objects.filter(pk=parent["id"], version=parent["version"]).first()
            if not obj or "create_child" not in allowed_actions(request.owner, obj):
                raise ConflictError("父任务已变化或不可拆分，请重新请求。")
    except DomainError as exc:
        return exc.message
    return ""


@transaction.atomic
def claim(device_id):
    device = AgentDevice.objects.select_for_update(of=("self",)).select_related("owner").get(pk=device_id)
    device_available(device)
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    expire_requests(device.requests.all())
    if device.requests.filter(status="running").exists():
        return None
    request = device.requests.select_for_update().filter(owner=device.owner, status="queued", kind__in=protocol.KINDS).order_by("created_at").first()
    if not request:
        return None
    reason = stale_reason(request)
    if reason:
        request.status, request.error = "failed", reason
        request.save(update_fields=["status", "error", "updated_at"])
        return None
    request.status, request.attempt_id = "running", uuid.uuid4()
    request.lease_expires_at = min(timezone.now() + timedelta(seconds=180), request.expires_at)
    request.save(update_fields=["status", "attempt_id", "lease_expires_at", "updated_at"])
    return request


def locked_attempt(device_id, request_id, attempt_id):
    device = AgentDevice.objects.select_for_update(of=("self",)).select_related("owner").get(pk=device_id)
    device_available(device)
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    request = device.requests.select_for_update().filter(pk=request_id, owner=device.owner, kind__in=protocol.KINDS).first()
    if not request:
        raise NotFound()
    if request.attempt_id != attempt_id:
        raise ConflictError("执行编号不匹配。", code="attempt_conflict")
    expire_requests(device.requests.filter(pk=request_id))
    request.refresh_from_db()
    return request


@transaction.atomic
def heartbeat(device_id, request_id, attempt_id, stopped=False):
    request = locked_attempt(device_id, request_id, attempt_id)
    if stopped:
        if request.status in ACTIVE:
            raise ConflictError("活动执行不能确认停止。")
        request.stopped_at = timezone.now()
    elif request.status == "running":
        if stale_reason(request):
            request.status = "expired"
        else:
            request.lease_expires_at = min(timezone.now() + timedelta(seconds=180), request.expires_at)
    request.save(update_fields=["status", "stopped_at", "lease_expires_at", "updated_at"])
    return request


def finish(device_id, request_id, attempt_id, *, result=None, error=""):
    outcome = _finish(device_id, request_id, attempt_id, result=result, error=error)
    # 先提交租约过期状态，再将迟到回传报告为冲突，避免异常回滚过期标记。
    if isinstance(outcome, ConflictError):
        raise outcome
    return outcome


@transaction.atomic
def _finish(device_id, request_id, attempt_id, *, result=None, error=""):
    request = locked_attempt(device_id, request_id, attempt_id)
    if request.status in ("succeeded", "failed") and request.result == result and request.error == error:
        return request
    if request.status != "running":
        return ConflictError("请求已结束，拒绝迟到或不同的回传。", code="request_terminal")
    if result is None:
        # 只接收固定错误码，避免本地异常、认证响应或环境变量泄漏。
        if error not in ("model_timeout", "model_unavailable", "invalid_result", "local_configuration", "local_failure"):
            raise ValidationFailure("本地错误须使用已定义的脱敏错误码。")
        request.status, request.error = "failed", error
    else:
        if request.kind == "agent_requirements" and stale_reason(request):
            return ConflictError("需求来源已变化，请重新导出。", code="version_conflict")
        if error:
            raise ValidationFailure("结果和错误不能同时提交。")
        validate(protocol.validate_result, request.kind, result)
        validate(protocol.validate_evidence, request.kind, result, request.input)
        if request.kind == "template_generate":
            _validate_template_steps(result["steps"])
        for field in ("content", "acceptance_criteria", "description", "comment", "markdown"):
            if field in result:
                assert_markdown_references_allowed(result[field], request.owner, field=field)
        request.status, request.result = "succeeded", result
    request.stopped_at = timezone.now()
    request.save(update_fields=["status", "result", "error", "stopped_at", "updated_at"])
    return request


@transaction.atomic
def cancel(actor, request_id):
    request = AssistanceRequest.objects.select_for_update().filter(pk=request_id, owner=actor, kind__in=protocol.KINDS).first()
    if not request:
        raise NotFound()
    if request.status in ACTIVE or request.status == "succeeded":
        if request.status != "running":
            request.stopped_at = timezone.now()
        request.status, request.result = "cancelled", None
        request.save(update_fields=["status", "result", "stopped_at", "updated_at"])
    return request
