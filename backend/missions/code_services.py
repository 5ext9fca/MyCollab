"""代码委派写入；由 missions.services 统一导出。"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from agent_bridge import services as bridge
from agent_bridge.code_protocol import CODE_KIND, PATCH_LIMIT, REPORT_LIMIT, repository_key, validate_manifest, validate_report, verify_bytes, validate_patch
from agent_bridge.protocol import INPUT_LIMIT, bounded_json, text
from agent_bridge.models import AgentDevice, AssistanceRequest
from common.exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from library.services import save_library_file
from library.references import assert_markdown_references_allowed
from .models import CodeExecution, Mission


def assert_code_current(execution):
    bridge.active_user(execution.actor)
    mission = Mission.objects.get(pk=execution.mission_id)
    if mission.status != 'InProgress' or mission.assignee_id != execution.actor_id:
        raise ConflictError('任务状态或认领者已变化，请重新委派。', code='execution_stale')
    if mission.version != execution.mission_version:
        raise ConflictError('任务版本已变化，请重新委派。', code='version_conflict')


@transaction.atomic
def create_code_execution(*, actor, mission_id, device_id, repository_key_value, expected_version, instructions, idempotency_key, previous_id=None):
    from .services import _acquire_team_lock
    _acquire_team_lock()
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    bridge.active_user(actor)
    bridge.validate(repository_key, repository_key_value)
    bridge.validate(text, instructions, 10000, True)
    payload = dict(mission=str(mission_id), device=str(device_id), repository=repository_key_value,
        version=expected_version, instructions=instructions, previous=str(previous_id) if previous_id else None)
    fingerprint = bridge.digest(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    old = AssistanceRequest.objects.filter(owner=actor, idempotency_key=idempotency_key).first()
    if old:
        if old.kind != CODE_KIND or old.payload_digest != fingerprint:
            raise ConflictError('幂等键已用于不同输入。', code='idempotency_conflict')
        return old.code_execution
    device = AgentDevice.objects.select_for_update().filter(pk=device_id, owner=actor).first()
    if not device:
        raise NotFound('设备不存在。')
    bridge.device_available(device)
    if CODE_KIND not in device.capabilities:
        raise ValidationFailure('设备未声明代码实现能力。')
    bridge.expire_requests(AssistanceRequest.objects.filter(owner=actor))
    if AssistanceRequest.objects.filter(owner=actor, status__in=bridge.ACTIVE).count() >= 3:
        raise ConflictError('最多同时保留 3 个活动请求。', code='request_limit')
    mission = Mission.objects.select_for_update().filter(pk=mission_id).first()
    if not mission:
        raise NotFound('任务不存在。')
    if mission.status != 'InProgress' or mission.assignee_id != actor.pk:
        raise PermissionDenied('只有当前认领者能委派自己的进行中任务。')
    if mission.version != expected_version:
        raise ConflictError('任务版本已变化。', code='version_conflict')
    previous = None
    if previous_id:
        previous = CodeExecution.objects.filter(pk=previous_id, actor=actor, mission=mission, repository_key=repository_key_value).first()
        if not previous or previous.request.status in bridge.ACTIVE:
            raise ValidationFailure('只能关联本任务/仓库已结束的本人执行。')
    snapshot = dict(mission={'id': str(mission.pk), 'title': mission.title, 'content': mission.content,
        'acceptance_criteria': mission.acceptance_criteria, 'version': mission.version},
        repository_key=repository_key_value, instructions=instructions)
    bridge.validate(bounded_json, snapshot, INPUT_LIMIT)
    request = AssistanceRequest.objects.create(owner=actor, device=device, kind=CODE_KIND, object_id=mission.pk,
        base_version=mission.version, input=snapshot, expires_at=timezone.now() + timedelta(minutes=30),
        idempotency_key=idempotency_key, payload_digest=fingerprint, retry_of=previous.request if previous else None)
    version = (CodeExecution.objects.filter(mission=mission, repository_key=repository_key_value).aggregate(n=Max('version'))['n'] or 0) + 1
    return CodeExecution.objects.create(request=request, mission=mission, actor=actor, mission_version=mission.version,
        repository_key=repository_key_value, version=version, previous=previous)


def _lock(device_id, request_id, attempt_id):
    from .services import _acquire_team_lock
    _acquire_team_lock()
    request = bridge.locked_attempt(device_id, request_id, attempt_id)
    if request.kind != CODE_KIND:
        raise ValidationFailure('此端点只接受代码执行。')
    execution = CodeExecution.objects.select_for_update().select_related('request', 'actor').get(request=request)
    return request, execution


def _current(request, execution, states):
    if request.status not in states:
        return ConflictError('当前阶段不允许此操作。', code='execution_terminal')
    try:
        assert_code_current(execution)
    except (ConflictError, PermissionDenied) as error:
        request.status = 'expired'
        request.save(update_fields=['status', 'updated_at'])
        return error
    return None


def _outcome(value):
    if isinstance(value, Exception):
        raise value
    return value


def stage_code_execution(*, device_id, request_id, attempt_id, manifest):
    bridge.validate(validate_manifest, manifest)
    return _outcome(_stage(device_id, request_id, attempt_id, manifest))


@transaction.atomic
def _stage(device_id, request_id, attempt_id, manifest):
    request, execution = _lock(device_id, request_id, attempt_id)
    if request.status in ('awaiting_selection', 'succeeded') and execution.manifest == manifest:
        return execution
    error = _current(request, execution, ('running',))
    if error:
        return error
    execution.manifest = manifest
    execution.save(update_fields=['manifest'])
    request.status, request.result = 'awaiting_selection', manifest
    request.expires_at, request.lease_expires_at, request.stopped_at = timezone.now() + timedelta(hours=24), None, timezone.now()
    request.save(update_fields=['status', 'result', 'expires_at', 'lease_expires_at', 'stopped_at', 'updated_at'])
    return execution


def publish_code_execution(*, device_id, request_id, attempt_id, patch_upload, report_upload):
    patch_data = patch_upload.read(PATCH_LIMIT + 1)
    report_data = report_upload.read(REPORT_LIMIT + 1)
    if len(patch_data) > PATCH_LIMIT or len(report_data) > REPORT_LIMIT:
        raise ValidationFailure('代码成果超出体积限制。')
    return _outcome(_publish(device_id, request_id, attempt_id, patch_data, report_data))


@transaction.atomic
def _publish(device_id, request_id, attempt_id, patch_data, report_data):
    request, execution = _lock(device_id, request_id, attempt_id)
    if not execution.manifest:
        raise ConflictError('须先提供本地成果清单。')
    patch_text = bridge.validate(verify_bytes, patch_data, 'patch', execution.manifest)
    report_text = bridge.validate(verify_bytes, report_data, 'report', execution.manifest)
    try:
        report = json.loads(report_text)
    except ValueError:
        raise ValidationFailure('报告不是合法 JSON。')
    bridge.validate(validate_report, report)
    assert_markdown_references_allowed(report['summary'], execution.actor, field='summary')
    if report['base_commit'] != execution.manifest['base_commit']:
        raise ValidationFailure('报告基线与清单不一致。')
    bridge.validate(validate_patch, patch_text, report)
    if request.status == 'succeeded' and execution.patch_id:
        return execution
    error = _current(request, execution, ('awaiting_selection',))
    if error:
        return error
    record = save_library_file(actor=execution.actor, upload=SimpleUploadedFile('changes.patch.txt', patch_data))
    try:
        execution.patch, execution.report, execution.published_at = record, report, timezone.now()
        execution.save(update_fields=['patch', 'report', 'published_at'])
        request.status = 'succeeded'
        request.save(update_fields=['status', 'updated_at'])
    except Exception:
        record.file.delete(save=False)
        raise
    return execution


@transaction.atomic
def cancel_code_execution(*, actor, execution_id):
    from .services import _acquire_team_lock
    _acquire_team_lock()
    execution = CodeExecution.objects.filter(pk=execution_id, actor=actor).first()
    if not execution:
        raise NotFound()
    if execution.submission_references.exists():
        raise ConflictError('成果已关联提交轮次，不能取消历史执行。')
    return bridge._cancel_request(actor, execution.request_id)
