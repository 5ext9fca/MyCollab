"""私有执行日志与结果待发箱：恢复上传，不恢复模型执行。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from .private_files import exclusive_lock, private_directory, private_file_descriptor

MAX_RECORDS = 100
MAX_BYTES = 512 * 1024
RETENTION_SECONDS = 24 * 3600


def atomic_json(path, value):
    raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('本地状态超出大小限制。')
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            private_file_descriptor(stream.fileno())
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class StateStore:
    def __init__(self, config_path, server, token):
        # 绑定服务器和设备，绝不把旧设备结果发给新服务器或新设备。
        identity = hashlib.sha256((server.rstrip('/') + '\0' + token).encode()).hexdigest()
        self.root = Path(config_path).parent / 'runner-state' / identity
        private_directory(self.root.parent)
        private_directory(self.root)

    def lock(self):
        return exclusive_lock(self.root / 'runner.lock')

    def status(self, state, **fields):
        records = list(self.records())
        atomic_json(self.root / 'status.json', {'state': state, 'updated_at': time.time(),
            'pending_results': sum(record['state'] == 'pending' for _, record in records),
            'rejected_results': sum(record['state'] == 'rejected' for _, record in records), **fields})

    def snapshot(self):
        path = self.root / 'status.json'
        value = self.read(path) if path.exists() else {'state': 'stopped'}
        records = list(self.records())
        return {**value, 'pending_results': sum(r['state'] == 'pending' for _, r in records),
                'rejected_results': sum(r['state'] == 'rejected' for _, r in records)}

    def read(self, path):
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('本地状态文件过大。')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('本地状态文件格式无效。')
        return value

    def records(self):
        for path in sorted(self.root.glob('result-*.json')):
            try:
                record = self.read(path)
            except FileNotFoundError:
                continue
            if time.time() - record['saved_at'] > RETENTION_SECONDS:
                path.unlink()
            else:
                yield path, record

    def begin(self, request):
        if len(list(self.records())) >= MAX_RECORDS:
            raise ValueError('本地待发箱已满，请先处理结果。')
        atomic_json(self.root / 'attempt.json', {'request_id': request['id'], 'attempt_id': request['attempt_id'], 'started_at': time.time()})
        self.status('running', request_id=request['id'])

    def save_result(self, request, payload):
        name = hashlib.sha256((request['id'] + ':' + request['attempt_id']).encode()).hexdigest()
        path = self.root / f'result-{name}.json'
        atomic_json(path, {'request_id': request['id'], 'payload': payload, 'saved_at': time.time(), 'state': 'pending'})
        return path

    def delivered(self, path):
        path.unlink(missing_ok=True)
        (self.root / 'attempt.json').unlink(missing_ok=True)

    def rejected(self, path, record, status):
        atomic_json(path, {**record, 'state': 'rejected', 'http_status': status})

    def recover(self, client):
        """服务端幂等回传；终态冲突留本机 24 小时，不重试模型或覆盖业务。"""
        for path, record in self.records():
            if record['state'] != 'pending':
                continue
            from urllib.error import HTTPError
            try:
                response = client.post(f"requests/{record['request_id']}/result/", record['payload'])
                if not isinstance(response, dict) or response.get("status") not in ("succeeded", "failed"):
                    return False
            except HTTPError as exc:
                if exc.code in (401, 403):
                    raise
                if 400 <= exc.code < 500 and exc.code != 429:
                    self.rejected(path, record, exc.code)
                else:
                    return False
            except (OSError, ValueError):
                return False
            else:
                self.delivered(path)
        return True
