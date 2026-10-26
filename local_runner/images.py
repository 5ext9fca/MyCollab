"""图像工作交接：生成不上传；用户显式选择后才上传同一文件。"""
import html
import json
import os
from pathlib import Path
import time
import tempfile
from urllib.error import HTTPError
from uuid import UUID

from backend.agent_bridge.image_protocol import inspect_png, validate_manifest
from .codex_image import normalize, run
from .opencode import Cancelled, LocalFailure


def output_directory(config, request_id, *, create=False):
    root = Path(config['image_output_dir']).expanduser().absolute()
    if root.is_symlink():
        raise ValueError('候选根目录不能是符号链接。')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'posix' and root.stat().st_mode & 0o077:
        raise ValueError('候选目录必须仅本人可访问，请 chmod 700。')
    target = root / str(UUID(request_id))
    if target.is_symlink():
        raise ValueError('执行目录不能是符号链接。')
    if create:
        target.mkdir(mode=0o700, exist_ok=False)
    if not target.is_dir():
        raise ValueError('本地执行不存在。')
    return target


def save_state(directory, value):
    path = directory / 'state.json'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, prefix='.state-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def retry(operation):
    for index in range(3):
        try:
            return operation()
        except HTTPError as exc:
            if exc.code < 500 or index == 2:
                raise
        except (OSError, ValueError):
            if index == 2:
                raise
        time.sleep(2 ** index)


def preview(directory, manifest):
    cards = []
    for item in manifest['candidates']:
        name = html.escape(item['name'], quote=True)
        cards.append(f'<figure><img src="{name}" alt="候选图片"><figcaption>{html.escape(item["key"])} · '
            f'{item["width"]} × {item["height"]}</figcaption></figure>')
    document = ('<!doctype html><html lang="zh"><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">'
        '<title>MyCollab 本地候选</title><style>body{font-family:system-ui;margin:32px;background:#f5f5f5}'
        'figure{padding:16px;background:white;border:1px solid #ddd;border-radius:12px}img{max-width:100%;max-height:650px}</style>'
        '<h1>本地候选预览</h1><p>图片尚未上传。请在终端用 --select 和 --keys 明确选择后上传。</p>'
        + ''.join(cards) + '</html>')
    path = directory / 'preview.html'
    path.write_text(document, encoding='utf-8')
    path.chmod(0o600)


def execute_image(client, request, config):
    endpoint = f"requests/{request['id']}/"
    attempt = {'attempt_id': request['attempt_id']}
    def heartbeat():
        try:
            return client.post(endpoint + 'heartbeat/', attempt)['status'] == 'running'
        except Exception:
            return False
    try:
        if config.get('image_adapter') != 'codex':
            raise LocalFailure('local_configuration')
        directory = output_directory(config, request['id'], create=True)
        references = []
        for index, item in enumerate(request['input'].get('references', [])):
            reference_id = str(UUID(item['id']))
            data = client.reference(endpoint + f'references/{reference_id}/', attempt)
            raw = directory / f'reference_{index}.source'
            raw.write_bytes(data)
            raw.chmod(0o600)
            normalized = directory / f'reference_{index}.png'
            normalize(raw, normalized)
            raw.unlink()
            references.append(normalized)
        manifest = run(request, directory, references, executable=config.get('codex', 'codex'), heartbeat=heartbeat)
        validate_manifest(manifest)
        state = {'server': client.url, 'request_id': request['id'], 'attempt_id': request['attempt_id'], 'manifest': manifest}
        save_state(directory, state)
        preview(directory, manifest)
    except Cancelled:
        try:
            client.post(endpoint + 'heartbeat/', {**attempt, 'stopped': True})
        except Exception:
            pass
        return
    except Exception as exc:
        code = exc.code if isinstance(exc, LocalFailure) else 'local_failure'
        try:
            retry(lambda: client.post(endpoint + 'result/', {**attempt, 'error': code}))
        except Exception:
            pass
        print('图像执行未完成；未自动重新生成。错误类别：' + code, flush=True)
        return
    try:
        retry(lambda: client.post(endpoint + 'candidates/', {**attempt, 'manifest': manifest}))
    except Exception:
        print('清单未确认回传。可在有效租约内用 --select 重传同一清单；不会重新生成。', flush=True)
    print(f'请先打开本地预览：{directory / "preview.html"}\n确认后使用 --select {request["id"]} --keys candidate_1（按实际选择填写）。', flush=True)


def select(client, config, request_id, keys):
    directory = output_directory(config, request_id)
    state_path = directory / 'state.json'
    if state_path.is_symlink() or state_path.stat().st_size > 16384:
        raise ValueError('本地执行记录无效。')
    state = json.loads(state_path.read_text())
    if state['server'] != client.url or state['request_id'] != str(UUID(request_id)):
        raise ValueError('本地执行与服务器不匹配。')
    manifest = validate_manifest(state['manifest'])
    candidates = {item['key']: item for item in manifest['candidates']}
    if not keys or len(keys) != len(set(keys)) or set(keys) - candidates.keys():
        raise ValueError('请明确指定预览中存在且不重复的候选编号。')
    if state.get('selected') and sorted(keys) != state['selected']:
        raise ValueError('已有选择不可覆盖；可重复上传同一选择集合。')
    files = []
    for key in keys:
        item = candidates[key]
        # 本地清单也不允许指向输出目录以外的文件。
        path = directory / item['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('候选文件无效。')
        data = path.read_bytes()
        if any(item[field] != value for field, value in inspect_png(data).items()):
            raise ValueError('候选文件已变化，不能上传。')
        files.append((key, data))
    endpoint = f'requests/{str(UUID(request_id))}/'
    attempt = {'attempt_id': str(UUID(state['attempt_id']))}
    retry(lambda: client.post(endpoint + 'candidates/', {**attempt, 'manifest': manifest}))
    retry(lambda: client.post(endpoint + 'selection/', {**attempt, 'keys': keys}))
    state['selected'] = sorted(keys)
    save_state(directory, state)
    for key, data in files:
        retry(lambda: client.upload(endpoint + f'candidates/{key}/upload/', attempt['attempt_id'], data))
    retry(lambda: client.post(endpoint + 'complete/', attempt))
    print('选中成果已上传；请回到 Mission 页面人工检查并提交。', flush=True)
