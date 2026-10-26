"""本机交互交接：命令执行前落盘，通信重试不重做模型或工具操作。"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from uuid import UUID, uuid4

from backend.agent_bridge.interaction_protocol import digest, validate_operation, validate_event, MESSAGE_LIMIT, MAX_EVENTS, TOTAL_LIMIT
from .code_workspace import allowed_path
from .opencode import LocalFailure


def safe_text(value):
    from .code_execution import public_text
    value = public_text(value)
    value = re.sub(r'(?i)(?:bearer\s+\S+|sk-[A-Za-z0-9_-]+|(?:api[_-]?key|token|password)\s*[:=]\s*\S+)', '[已隐藏凭据]', value)
    value = value[:MESSAGE_LIMIT]
    while len(json.dumps(value, ensure_ascii=False).encode()) > 6000:
        value = value[:len(value) // 2]
    return value


def native_path(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value):
        raise LocalFailure('invalid_result')
    return value


class Interaction:
    def __init__(self, client, request, native, session_id, workspace, writable_paths, directory):
        self.client, self.native = client, native
        self.session_id = native_path(session_id)
        self.base = '/api/session/' + self.session_id
        self.endpoint = f"requests/{str(UUID(request['id']))}/interaction/"
        self.binding = {'attempt_id': str(UUID(request['attempt_id'])), 'session_nonce': str(uuid4())}
        self.workspace, self.paths = Path(workspace).resolve(), writable_paths
        self.path = Path(directory) / 'interaction.json'
        if self.path.exists():
            raise LocalFailure('local_configuration')
        self.commands, self.permissions, self.events, self.acks = {}, {}, [], []
        self.event_count = self.event_bytes = 0
        self.save()
        client.post(self.endpoint + 'open/', {**self.binding, 'supports_followup': True, 'supports_permissions': True})

    def save(self):
        data = {'binding': self.binding, 'native_session': self.session_id, 'commands': self.commands,
            'permissions': self.permissions, 'events': self.events, 'acknowledgements': self.acks}
        temporary = self.path.with_suffix('.tmp')
        with open(temporary, 'w', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def event(self, kind, payload):
        value = {'event_id': str(uuid4()), 'kind': kind, 'payload': payload}
        validate_event(value)
        size = len(json.dumps(value, ensure_ascii=False).encode())
        if self.event_count >= MAX_EVENTS or self.event_bytes + size > TOTAL_LIMIT:
            return False
        self.event_count += 1; self.event_bytes += size
        self.events.append(value)
        self.save()
        return True

    def exchange(self, close=False):
        # 失败时保留相同事件与 ACK；不自动重做本地操作。
        response = self.client.post(self.endpoint + 'exchange/', {**self.binding,
            'events': self.events[:20], 'acknowledgements': self.acks[:100], 'close': close and len(self.events) <= 20})
        self.events = self.events[20:]; self.acks = self.acks[100:]
        self.save()
        for command in response['commands']:
            self.apply(command)
        return response.get('closed', False)

    def operation(self, item):
        if item.get('sessionID') != self.session_id or item.get('action') != 'edit':
            raise ValueError('不允许的会话或操作')
        paths = []
        for resource in item.get('resources', []):
            path = Path(resource)
            if path.is_absolute():
                relative = path.relative_to(self.workspace).as_posix()
            else:
                relative = resource
            if not allowed_path(relative, self.paths):
                raise ValueError('超出本地白名单')
            target = self.workspace / relative
            if not target.resolve().is_relative_to(self.workspace) or any(parent.is_symlink() for parent in [target, *target.parents]):
                raise ValueError('禁止符号链接或外部目录')
            paths.append(relative)
        return validate_operation({'action': 'edit', 'paths': paths})

    def reply(self, native_id, decision):
        self.native.call('POST', self.base + '/permission/' + native_path(native_id) + '/reply', {'decision': decision})

    def poll_permissions(self):
        current = self.native.call('GET', self.base + '/permission')['data']
        current_ids = {item['id'] for item in current}
        for key, saved in self.permissions.items():
            if saved['status'] != 'pending':
                continue
            if saved['native_id'] not in current_ids:
                saved['status'] = 'cancelled'
                self.event('permission_closed', {'permission_id': key, 'outcome': 'cancelled'})
            elif time.time() >= saved['deadline']:
                self.reply(saved['native_id'], 'reject')
                saved['status'] = 'expired'
                self.event('permission_closed', {'permission_id': key, 'outcome': 'expired'})
        known = {value['native_id'] for value in self.permissions.values()}
        for item in current:
            if item['id'] in known:
                continue
            try:
                operation = self.operation(item)
            except (ValueError, TypeError):
                self.reply(item['id'], 'reject')
                continue
            key = str(uuid4())
            self.permissions[key] = {'native_id': item['id'], 'native_digest': digest(item),
                'operation_digest': digest(operation), 'deadline': time.time() + 120, 'status': 'pending'}
            if not self.event('permission_requested', {'permission_id': key, 'operation': operation}):
                self.reply(item['id'], 'reject')
                self.permissions[key]['status'] = 'denied'
        self.save()

    def apply(self, command):
        key = str(UUID(command['command_id']))
        fingerprint = digest(command)
        old = self.commands.get(key)
        if old:
            if old['digest'] != fingerprint or old['status'] == 'processing':
                raise LocalFailure('invalid_result')
            self.acks.append({'command_id': key, 'status': old['status']})
            return
        if len(self.commands) >= 100:
            raise LocalFailure('invalid_result')
        self.commands[key] = {'digest': fingerprint, 'status': 'processing'}
        self.save()
        status = 'rejected'
        if datetime.fromisoformat(command['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc):
            payload = command['payload']
            if command['kind'] == 'followup':
                if set(payload) != {'text'} or not isinstance(payload['text'], str) or not 0 < len(payload['text']) <= MESSAGE_LIMIT:
                    raise LocalFailure('invalid_result')
                self.last_prompt = time.time() * 1000
                self.native.call('POST', self.base + '/prompt', {'id': 'msg_' + UUID(key).hex,
                    'text': payload['text'], 'delivery': 'steer'})
                status = 'applied'
            elif command['kind'] == 'permission_reply':
                saved = self.permissions.get(payload['permission_id'])
                if saved and saved['status'] == 'pending' and saved['deadline'] > time.time() and payload['operation_digest'] == saved['operation_digest']:
                    current = self.native.call('GET', self.base + '/permission')['data']
                    item = next((item for item in current if item['id'] == saved['native_id']), None)
                    if item and digest(item) == saved['native_digest'] and digest(self.operation(item)) == saved['operation_digest']:
                        if payload['decision'] not in ('approve', 'deny'):
                            raise LocalFailure('invalid_result')
                        approved = payload['decision'] == 'approve'
                        self.reply(saved['native_id'], 'once' if approved else 'reject')
                        saved['status'] = 'approved' if approved else 'denied'
                        self.event('permission_closed', {'permission_id': payload['permission_id'], 'outcome': saved['status']})
                        status = 'applied'
        self.commands[key]['status'] = status
        self.acks.append({'command_id': key, 'status': status})
        self.save()
