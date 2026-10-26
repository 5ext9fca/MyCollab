"""图像委派业务实现；公开写入口由 missions.services 导出。"""
import hashlib
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from agent_bridge import services as bridge
from agent_bridge.image_protocol import IMAGE_KINDS, MAX_IMAGE_BYTES, inspect_png, validate_manifest
from agent_bridge.models import AgentDevice, AssistanceRequest
from agent_bridge.protocol import INPUT_LIMIT, bounded_json, text
from common.exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from library.models import LibraryFile
from library.services import save_library_file
from .models import DesignElement, ExecutionCandidate, Mission, MissionExecution


def assert_execution_current(execution):
    bridge.active_user(execution.actor)
    mission = Mission.objects.get(pk=execution.mission_id)
    if mission.status != 'InProgress' or mission.assignee_id != execution.actor_id:
        raise ConflictError('任务状态或认领者已变化，请重新委派。', code='execution_stale')
    if mission.version != execution.mission_version:
        raise ConflictError('任务版本已变化，请重新委派。', code='version_conflict')
    asset = DesignElement.objects.get(pk=execution.asset_id)
    if asset.archived or asset.version != execution.asset_version or not mission.assets.filter(pk=asset.pk).exists():
        raise ConflictError('资产版本或关联已变化，请重新委派。', code='execution_stale')
    expected = {item['id'] for item in execution.request.input.get('references', [])}
    actual = {str(item.pk) for item in execution.reference_files.filter(owner_id=execution.actor_id)}
    if expected != actual:
        raise ConflictError('参考素材已被删除，请重新委派。', code='execution_stale')


@transaction.atomic
def create_execution(*, actor, mission_id, asset_id, device_id, kind, expected_version, asset_version,
                     instructions, reference_ids, idempotency_key, previous_id=None):
    from .services import _acquire_team_lock
    _acquire_team_lock()
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    bridge.active_user(actor)
    if kind not in IMAGE_KINDS:
        raise ValidationFailure('请选择图像生成或编辑。')
    bridge.validate(text, instructions, 10000, True)
    if not isinstance(reference_ids, list) or len(reference_ids) > 4 or len(set(reference_ids)) != len(reference_ids):
        raise ValidationFailure('最多选择 4 张不重复的本人参考图片。')
    if kind == 'image_edit' and not reference_ids:
        raise ValidationFailure('图像编辑至少需要一张参考图片。')
    payload = dict(mission=str(mission_id), asset=str(asset_id), device=str(device_id), kind=kind,
        mission_version=expected_version, asset_version=asset_version, instructions=instructions,
        references=[str(i) for i in reference_ids], previous=str(previous_id) if previous_id else None)
    fingerprint = bridge.digest(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    old = AssistanceRequest.objects.filter(owner=actor, idempotency_key=idempotency_key).first()
    if old:
        if old.kind not in IMAGE_KINDS or old.payload_digest != fingerprint:
            raise ConflictError('幂等键已用于不同输入。', code='idempotency_conflict')
        return old.execution
    device = AgentDevice.objects.select_for_update().filter(pk=device_id, owner=actor).first()
    if not device:
        raise NotFound('设备不存在。')
    bridge.device_available(device)
    if kind not in device.capabilities:
        raise ValidationFailure('设备未声明所选图像能力。')
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
    asset = mission.assets.filter(pk=asset_id, kind='Asset', archived=False).first()
    if not asset:
        raise ValidationFailure('须选择当前任务关联的未归档资产。')
    if asset.version != asset_version:
        raise ConflictError('资产版本已变化。', code='version_conflict')
    references = []
    for file_id in reference_ids:
        item = LibraryFile.objects.filter(pk=file_id, owner=actor, content_type__in=('image/png', 'image/jpeg', 'image/webp')).first()
        if not item or item.size > MAX_IMAGE_BYTES:
            raise ValidationFailure('参考图片不存在、不属于本人或超出限制。')
        references.append(item)
    if sum(item.size for item in references) > 40 * 1024 * 1024:
        raise ValidationFailure('参考图片总量最多 40 MiB。')
    previous = None
    if previous_id:
        previous = MissionExecution.objects.filter(pk=previous_id, actor=actor, mission=mission, asset=asset).first()
        if not previous or previous.request.status in bridge.ACTIVE:
            raise ValidationFailure('只能关联本任务/资产已结束的本人执行。')
    snapshot = dict(mission={'id': str(mission.pk), 'title': mission.title, 'content': mission.content,
        'acceptance_criteria': mission.acceptance_criteria, 'version': mission.version},
        asset={'id': str(asset.pk), 'title': asset.title, 'content': asset.content, 'version': asset.version},
        instructions=instructions, references=[{'id': str(f.pk), 'name': f.original_name, 'size': f.size,
        'content_type': f.content_type} for f in references])
    bridge.validate(bounded_json, snapshot, INPUT_LIMIT)
    request = AssistanceRequest.objects.create(owner=actor, device=device, kind=kind, object_id=mission.pk,
        base_version=mission.version, input=snapshot, expires_at=timezone.now() + timedelta(minutes=30),
        idempotency_key=idempotency_key, payload_digest=fingerprint, retry_of=previous.request if previous else None)
    version = (MissionExecution.objects.filter(mission=mission, asset=asset).aggregate(n=Max('version'))['n'] or 0) + 1
    execution = MissionExecution.objects.create(request=request, mission=mission, asset=asset, actor=actor,
        mission_version=mission.version, asset_version=asset.version, version=version, previous=previous)
    execution.reference_files.set(references)
    return execution


def _lock_execution(device_id, request_id, attempt_id):
    from .services import _acquire_team_lock
    _acquire_team_lock()
    request = bridge.locked_attempt(device_id, request_id, attempt_id)
    if request.kind not in IMAGE_KINDS:
        raise ValidationFailure('此端点只接受图像执行。')
    execution = MissionExecution.objects.select_for_update().select_related('request', 'actor').get(request=request)
    return request, execution


def _current(request, execution, states):
    if request.status not in states:
        return ConflictError('执行已结束或当前阶段不允许此操作。', code='execution_terminal')
    try:
        assert_execution_current(execution)
    except (ConflictError, PermissionDenied) as error:
        request.status = 'expired'
        request.save(update_fields=['status', 'updated_at'])
        return error
    return None


def _outcome(value):
    # 过期更新先提交，再向客户端报告拒绝，避免回滚过期标记。
    if isinstance(value, Exception):
        raise value
    return value


def publish_execution_candidates(*, device_id, request_id, attempt_id, manifest):
    bridge.validate(validate_manifest, manifest)
    return _outcome(_publish(device_id, request_id, attempt_id, manifest))


@transaction.atomic
def _publish(device_id, request_id, attempt_id, manifest):
    request, execution = _lock_execution(device_id, request_id, attempt_id)
    if request.status in ('awaiting_selection', 'succeeded') and request.result == manifest:
        return execution
    error = _current(request, execution, ('running',))
    if error:
        return error
    for candidate in manifest['candidates']:
        ExecutionCandidate.objects.create(execution=execution, **candidate)
    request.status, request.result = 'awaiting_selection', manifest
    request.expires_at = timezone.now() + timedelta(hours=24)
    request.lease_expires_at = None
    request.stopped_at = timezone.now()
    request.save(update_fields=['status', 'result', 'expires_at', 'lease_expires_at', 'stopped_at', 'updated_at'])
    return execution


def select_execution_candidates(*, device_id, request_id, attempt_id, keys):
    if not isinstance(keys, list) or not 1 <= len(keys) <= 4 or len(set(keys)) != len(keys):
        raise ValidationFailure('明确选择 1–4 个不重复的候选编号。')
    return _outcome(_select(device_id, request_id, attempt_id, keys))


@transaction.atomic
def _select(device_id, request_id, attempt_id, keys):
    request, execution = _lock_execution(device_id, request_id, attempt_id)
    if request.status == 'succeeded' and sorted(execution.selected_ids) == sorted(keys):
        return execution
    error = _current(request, execution, ('awaiting_selection',))
    if error:
        return error
    if execution.selected_ids:
        if sorted(execution.selected_ids) != sorted(keys):
            raise ConflictError('选择集合已确认，不可覆盖；需要新候选请重新委派。')
        return execution
    if set(keys) - set(execution.candidates.values_list('key', flat=True)):
        raise ValidationFailure('选中的候选不存在。')
    execution.selected_ids = sorted(keys)
    execution.save(update_fields=['selected_ids'])
    return execution


def upload_execution_candidate(*, device_id, request_id, attempt_id, key, upload):
    if getattr(upload, 'size', 0) > MAX_IMAGE_BYTES:
        raise ValidationFailure('单张成果不得超过 20 MiB。')
    data = upload.read(MAX_IMAGE_BYTES + 1)
    info = bridge.validate(inspect_png, data)
    upload.seek(0)
    return _outcome(_upload(device_id, request_id, attempt_id, key, upload, info))


@transaction.atomic
def _upload(device_id, request_id, attempt_id, key, upload, info):
    request, execution = _lock_execution(device_id, request_id, attempt_id)
    candidate = execution.candidates.select_for_update().filter(key=key).first()
    if not candidate or key not in execution.selected_ids:
        raise PermissionDenied('只能上传本机明确选择的候选。')
    if any(getattr(candidate, field) != value for field, value in info.items()):
        raise ValidationFailure('文件尺寸、大小或摘要与候选清单不一致。')
    if request.status == 'succeeded' and candidate.file_id:
        return candidate
    error = _current(request, execution, ('awaiting_selection',))
    if error:
        return error
    if candidate.file_id:
        return candidate
    upload.name = candidate.name
    record = save_library_file(actor=execution.actor, upload=upload)
    try:
        candidate.file, candidate.uploaded_at = record, timezone.now()
        candidate.save(update_fields=['file', 'uploaded_at'])
    except Exception:
        record.file.delete(save=False)
        raise
    return candidate


def complete_execution(*, device_id, request_id, attempt_id):
    return _outcome(_complete(device_id, request_id, attempt_id))


@transaction.atomic
def _complete(device_id, request_id, attempt_id):
    request, execution = _lock_execution(device_id, request_id, attempt_id)
    if request.status == 'succeeded':
        return execution
    error = _current(request, execution, ('awaiting_selection',))
    if error:
        return error
    if not execution.selected_ids or execution.candidates.filter(key__in=execution.selected_ids, file__isnull=False).count() != len(execution.selected_ids):
        raise ConflictError('选中的成果尚未全部上传，不能标记完成。')
    request.status = 'succeeded'
    request.save(update_fields=['status', 'updated_at'])
    return execution


@transaction.atomic
def cancel_execution(*, actor, execution_id):
    from .services import _acquire_team_lock
    _acquire_team_lock()
    execution = MissionExecution.objects.select_related('request').filter(pk=execution_id, actor=actor).first()
    if not execution:
        raise NotFound()
    if execution.candidates.filter(submission_references__isnull=False).exists():
        raise ConflictError('成果已关联提交轮次，不能取消历史执行。')
    return bridge._cancel_request(actor, execution.request_id)


def execution_reference(*, device_id, request_id, attempt_id, file_id):
    with transaction.atomic():
        request, execution = _lock_execution(device_id, request_id, attempt_id)
        error = _current(request, execution, ('running',))
        if not error:
            result = execution.reference_files.filter(pk=file_id, owner=execution.actor).first()
            if not result:
                raise NotFound('参考素材未授权给本次执行。')
    if error:
        raise error
    return result
