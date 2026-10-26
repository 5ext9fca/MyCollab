"""浏览器与本地 Runner 的有界交互协议，不透传 Agent 原始事件。"""
import hashlib
import json
from uuid import UUID

from .protocol import ProtocolError, bounded_json, fields, text
from .code_protocol import relative_path

EVENT_LIMIT = 8192
TOTAL_LIMIT = 1024 * 1024
MAX_EVENTS = 1000
MAX_COMMANDS = 100
MESSAGE_LIMIT = 4000
PERMISSION_SECONDS = 120


def identifier(value):
    if not isinstance(value, str):
        raise ProtocolError('交互标识必须是 UUID。')
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError as exc:
        raise ProtocolError('交互标识必须是规范 UUID。') from exc
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate_operation(value):
    """仅允许展示仓库内文件编辑审批，原始工具参数和本机路径不能上报。"""
    bounded_json(value, EVENT_LIMIT)
    fields(value, ('action', 'paths'))
    if value['action'] != 'edit':
        raise ProtocolError('当前只支持本地白名单内的文件编辑审批。')
    paths = value['paths']
    if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
        raise ProtocolError('审批须包含 1–20 个相对路径。')
    for path in paths:
        relative_path(path)
        if any(part.startswith('.env') or part.startswith('opencode.json') for part in path.split('/')):
            raise ProtocolError('禁止审批认证或 Agent 配置文件。')
    if len(set(paths)) != len(paths):
        raise ProtocolError('审批路径不能重复。')
    return value


def validate_event(value):
    bounded_json(value, EVENT_LIMIT)
    fields(value, ('event_id', 'kind', 'payload'))
    identifier(value['event_id'])
    payload = value['payload']
    if value['kind'] == 'assistant_message':
        fields(payload, ('text',))
        text(payload['text'], MESSAGE_LIMIT, True)
    elif value['kind'] == 'permission_requested':
        fields(payload, ('permission_id', 'operation'))
        identifier(payload['permission_id'])
        validate_operation(payload['operation'])
    elif value['kind'] == 'permission_closed':
        fields(payload, ('permission_id', 'outcome'))
        identifier(payload['permission_id'])
        if payload['outcome'] not in ('approved', 'denied', 'expired', 'cancelled'):
            raise ProtocolError('审批结果无效。')
    else:
        raise ProtocolError('不支持的交互事件。')
    return value
