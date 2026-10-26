"""私有交互交接：不会调用模型，也不会扩大本地工具权限。"""
from datetime import timedelta
import json

from django.db import transaction
from django.utils import timezone

from common.exceptions import ConflictError, NotFound, ValidationFailure
from . import interaction_protocol as protocol
from .models import AgentDevice, AssistanceRequest, InteractionSession, InteractionEvent, InteractionPermission, InteractionCommand


def bridge():
    from . import services
    return services


def active(request, session=None):
    now = timezone.now()
    return (request.status == 'running' and request.expires_at > now and request.lease_expires_at is not None
        and request.lease_expires_at > now and not bridge().stale_reason(request)
        and (session is None or (session.attempt_id == request.attempt_id and not session.closed_at)))


def require_active(request, session=None):
    if not active(request, session):
        raise ConflictError('执行或交互已结束，不能发送指令。', code='interaction_closed')


def locked_browser(actor, request_id):
    bridge().active_user(actor)
    target = AssistanceRequest.objects.filter(pk=request_id, owner=actor).first()
    if not target:
        raise NotFound()
    device = AgentDevice.objects.select_for_update().get(pk=target.device_id)
    bridge().device_available(device)
    request = AssistanceRequest.objects.select_for_update().get(pk=target.pk, owner=actor)
    return request


def session_for(request, nonce):
    session = InteractionSession.objects.filter(request=request, attempt_id=request.attempt_id, session_nonce=nonce).first()
    if not session:
        raise ConflictError('交互会话不匹配。', code='interaction_session_conflict')
    return session


@transaction.atomic
def open_interaction(device_id, request_id, attempt_id, session_nonce, supports_followup, supports_permissions):
    request = bridge().locked_attempt(device_id, request_id, attempt_id)
    require_active(request)
    if request.kind != 'code_implement':
        raise ValidationFailure('当前适配器只为代码执行提供交互。')
    existing = InteractionSession.objects.filter(request=request).first()
    if existing:
        if (existing.attempt_id, existing.session_nonce, existing.supports_followup, existing.supports_permissions) != (attempt_id, session_nonce, supports_followup, supports_permissions) or existing.closed_at:
            raise ConflictError('不能替换已有交互会话。')
        return {'opened': True}
    InteractionSession.objects.create(request=request, attempt_id=attempt_id, session_nonce=session_nonce,
        supports_followup=supports_followup, supports_permissions=supports_permissions)
    return {'opened': True}


def expire_pending(session):
    now = timezone.now()
    session.permissions.filter(status__in=['pending', 'decided'], expires_at__lte=now).update(status='expired')
    session.commands.filter(status='queued', expires_at__lte=now).update(status='expired')


def record_event(session, event):
    bridge().validate(protocol.validate_event, event)
    fingerprint = protocol.digest(event)
    old = session.events.filter(event_id=event['event_id']).first()
    if old:
        if old.payload_digest != fingerprint:
            raise ConflictError('重复事件内容不同。')
        return old.seq
    size = len(json.dumps(event, ensure_ascii=False).encode())
    if session.event_count >= protocol.MAX_EVENTS or session.event_bytes + size > protocol.TOTAL_LIMIT:
        raise ConflictError('交互事件已达上限。', code='interaction_limit')
    kind, payload = event['kind'], event['payload']
    if kind == 'permission_requested':
        if not session.supports_permissions:
            raise ValidationFailure('该会话不支持权限审批。')
        if session.permissions.filter(permission_id=payload['permission_id']).exists():
            raise ConflictError('权限请求不能重复创建。')
        session.permissions.create(permission_id=payload['permission_id'], operation=payload['operation'],
            operation_digest=protocol.digest(payload['operation']), expires_at=min(session.request.expires_at, timezone.now() + timedelta(seconds=protocol.PERMISSION_SECONDS)))
    elif kind == 'permission_closed':
        permission = session.permissions.filter(permission_id=payload['permission_id']).first()
        if not permission:
            raise NotFound()
        if payload['outcome'] == 'approved' and (permission.decision != 'approve' or permission.status != 'decided' or permission.expires_at <= timezone.now()):
            raise ConflictError('没有有效的单次批准。')
        if permission.status in ('approved', 'denied', 'cancelled'):
            raise ConflictError('权限请求已经结束。')
        permission.status = payload['outcome']
        permission.save(update_fields=['status'])
    session.event_count += 1
    session.event_bytes += size
    item = session.events.create(event_id=event['event_id'], seq=session.event_count, kind=kind,
        payload=payload, payload_digest=fingerprint)
    session.save(update_fields=['event_count', 'event_bytes'])
    return item.seq


@transaction.atomic
def exchange_interaction(device_id, request_id, attempt_id, session_nonce, events, acknowledgements, close=False):
    request = bridge().locked_attempt(device_id, request_id, attempt_id)
    session = session_for(request, session_nonce)
    require_active(request, session)
    expire_pending(session)
    sequences = [record_event(session, event) for event in events]
    for ack in acknowledgements:
        command = session.commands.filter(command_id=ack['command_id']).first()
        if not command:
            raise NotFound()
        if command.status in ('applied', 'rejected'):
            if command.status != ack['status']:
                raise ConflictError('命令处理结果不一致。')
            continue
        if command.status == 'expired' and ack['status'] == 'applied':
            raise ConflictError('过期命令不可执行。')
        command.status = ack['status']
        command.acknowledged_at = timezone.now()
        command.save(update_fields=['status', 'acknowledged_at'])
    if close and not session.commands.filter(status='queued').exists():
        session.closed_at = timezone.now()
        session.save(update_fields=['closed_at'])
        session.commands.filter(status='queued').update(status='expired')
        session.permissions.filter(status__in=['pending', 'decided']).update(status='cancelled')
    commands = list(session.commands.filter(status='queued').values('command_id', 'kind', 'payload', 'expires_at'))
    return {'sequences': sequences, 'commands': commands, 'closed': bool(session.closed_at)}


@transaction.atomic
def interaction_state(actor, request_id, after=0):
    request = locked_browser(actor, request_id)
    session = InteractionSession.objects.filter(request=request).first()
    if not session:
        return {'available': False, 'active': False, 'events': [], 'commands': [], 'permissions': []}
    expire_pending(session)
    events = list(session.events.filter(seq__gt=after).values('seq', 'kind', 'payload', 'created_at')[:100])
    return {'available': True, 'active': active(request, session), 'attempt_id': session.attempt_id,
        'session_nonce': session.session_nonce, 'supports_followup': session.supports_followup,
        'supports_permissions': session.supports_permissions, 'events': events,
        'next_cursor': events[-1]['seq'] if events else after, 'has_more': bool(events and session.event_count > events[-1]['seq']),
        'permissions': list(session.permissions.order_by('created_at').values('permission_id', 'operation', 'operation_digest', 'status', 'expires_at', 'decision')),
        'commands': list(session.commands.values('command_id', 'kind', 'payload', 'status', 'created_at'))}


@transaction.atomic
def create_interaction_command(actor, request_id, attempt_id, session_nonce, command_id, kind, payload):
    request = locked_browser(actor, request_id)
    session = session_for(request, session_nonce)
    if request.attempt_id != attempt_id:
        raise ConflictError('执行编号不匹配。')
    require_active(request, session)
    bridge().validate(protocol.bounded_json, payload, protocol.EVENT_LIMIT)
    fingerprint = protocol.digest({'kind': kind, 'payload': payload})
    old = session.commands.filter(command_id=command_id).first()
    if old:
        if old.payload_digest != fingerprint:
            raise ConflictError('幂等键对应不同的命令。')
        return {'command_id': old.command_id, 'status': old.status}
    expire_pending(session)
    if session.command_count >= protocol.MAX_COMMANDS:
        raise ConflictError('本次执行交互命令已达上限。', code='interaction_limit')
    expiry = min(request.expires_at, timezone.now() + timedelta(seconds=120))
    if kind == 'followup':
        if not session.supports_followup:
            raise ValidationFailure('当前会话不支持追问。')
        bridge().validate(protocol.fields, payload, ('text',))
        bridge().validate(protocol.text, payload['text'], protocol.MESSAGE_LIMIT, True)
    elif kind == 'permission_reply':
        bridge().validate(protocol.fields, payload, ('permission_id', 'operation_digest', 'decision'))
        bridge().validate(protocol.identifier, payload['permission_id'])
        if not session.supports_permissions or payload['decision'] not in ('approve', 'deny'):
            raise ValidationFailure('仅支持一次批准或拒绝。')
        permission = session.permissions.filter(permission_id=payload['permission_id'], status='pending').first()
        if not permission or permission.expires_at <= timezone.now() or permission.operation_digest != payload['operation_digest']:
            raise ConflictError('权限请求过期、已处理或操作摘要不符。')
        permission.status, permission.decision = 'decided', payload['decision']
        permission.save(update_fields=['status', 'decision'])
        expiry = min(expiry, permission.expires_at)
    else:
        raise ValidationFailure('未知交互命令。')
    command = session.commands.create(command_id=command_id, kind=kind, payload=payload, payload_digest=fingerprint, expires_at=expiry)
    session.command_count += 1
    session.save(update_fields=['command_count'])
    return {'command_id': command.command_id, 'status': command.status}
