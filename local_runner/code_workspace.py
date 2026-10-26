"""从已配置本地 Git 基线导出独立副本；不修改源仓库。"""
import io
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

from backend.agent_bridge.code_protocol import relative_path, repository_key, PATCH_LIMIT
from .opencode import LocalFailure

SNAPSHOT_LIMIT = 100 * 1024 * 1024
BLOCKED_PARTS = {'.git', '.opencode', '.ssh', '.aws', '.codex', 'node_modules', '.venv'}
BLOCKED_NAMES = {'opencode.json', 'opencode.jsonc', 'auth.json', 'credentials', '.npmrc', '.netrc'}


def excluded(path):
    return any(part.lower() in BLOCKED_PARTS or part.lower() in BLOCKED_NAMES or part.startswith('.env') for part in PurePosixPath(path).parts)


def git(directory, *args, limit=SNAPSHOT_LIMIT):
    # 禁止外部 diff/textconv/hooks 和用户 Git 配置，不使用凭据或远端。
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'MYCOLLAB_'))}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    process = subprocess.Popen(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
        '-c', 'core.quotePath=false', '-C', str(directory), *args], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        result = process.stdout.read(limit + 1)
        if len(result) > limit:
            raise LocalFailure('invalid_result')
        if process.wait(timeout=30):
            raise LocalFailure('local_configuration')
        return result
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def configuration(config, key):
    repository_key(key)
    value = config.get('repositories', {}).get(key)
    if not isinstance(value, dict):
        raise LocalFailure('local_configuration')
    repository = Path(value.get('path', '')).expanduser()
    if not repository.is_absolute() or not repository.is_dir():
        raise LocalFailure('local_configuration')
    if type(value.get('interactive', False)) is not bool:
        raise LocalFailure('local_configuration')
    allowed = value.get('writable_paths')
    if not isinstance(allowed, list) or not allowed or len(allowed) > 50:
        raise LocalFailure('local_configuration')
    for path in allowed:
        relative_path(path)
        if excluded(path) or '*' in path or '?' in path:
            raise LocalFailure('local_configuration')
    checks = value.get('verification', [])
    if not isinstance(checks, list) or len(checks) > 20:
        raise LocalFailure('local_configuration')
    ids = set()
    for check in checks:
        repository_key(check['id'])
        if check['id'] in ids or not isinstance(check.get('label'), str) or not 1 <= len(check['label']) <= 200:
            raise LocalFailure('local_configuration')
        ids.add(check['id'])
        argv = check.get('argv')
        if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a or '\x00' in a for a in argv):
            raise LocalFailure('local_configuration')
        if type(check.get('timeout', 120)) is not int or not 1 <= check.get('timeout', 120) <= 900:
            raise LocalFailure('local_configuration')
    return {**value, 'path': repository, 'verification': checks}


def allowed_path(path, permitted):
    relative_path(path)
    return not excluded(path) and any(path == item or path.startswith(item + '/') for item in permitted)


def prepare(repository, destination):
    baseline = repository.get('baseline', 'HEAD')
    if not isinstance(baseline, str) or baseline.startswith('-') or len(baseline) > 200:
        raise LocalFailure('local_configuration')
    source = repository['path']
    commit = git(source, 'rev-parse', '--verify', baseline + '^{commit}', limit=256).decode().strip()
    tree = git(source, 'ls-tree', '-rz', commit)
    expected = {}
    for entry in tree.split(b'\x00'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, kind, object_id = metadata.split(b' ')
        name = raw_name.decode('utf-8')
        if excluded(name):
            continue
        relative_path(name)
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise LocalFailure('local_configuration')
        expected[name] = object_id.decode()
    archive = git(source, 'archive', '--format=tar', commit)
    destination.mkdir(mode=0o700, exist_ok=False)
    total = count = 0
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as bundle:
        for member in bundle:
            name = member.name.rstrip('/')
            if excluded(name):
                continue
            relative_path(name)
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise LocalFailure('local_configuration')
            total += member.size
            count += 1
            if total > SNAPSHOT_LIMIT or count > 20000:
                raise LocalFailure('local_configuration')
            target = destination / name
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with bundle.extractfile(member) as stream:
                    data = stream.read()
                object_id = hashlib.new('sha256' if len(commit) == 64 else 'sha1', b'blob ' + str(len(data)).encode() + b'\x00' + data).hexdigest()
                if expected.get(name) != object_id or name in seen:
                    raise LocalFailure('local_configuration')
                seen.add(name)
                target.write_bytes(data)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
    # export-ignore/export-subst 等属性不能悄悄改变补丁基线。
    if seen != set(expected):
        raise LocalFailure('local_configuration')
    git(destination, 'init', '-q', '--object-format=' + ('sha256' if len(commit) == 64 else 'sha1'))
    git(destination, 'add', '--all', '--force')
    git(destination, '-c', 'user.name=MyCollab Local', '-c', 'user.email=local@invalid', 'commit', '-q', '--allow-empty', '-m', '隔离基线')
    return commit


def changes(directory, permitted):
    # 读取实际树，防止模型输出中的文件名掩盖越界写入。
    for root, dirs, files in os.walk(directory, followlinks=False):
        if Path(root) == directory:
            dirs[:] = [d for d in dirs if d != '.git']
        for name in dirs + files:
            path = Path(root) / name
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                raise LocalFailure('invalid_result')
    git(directory, 'add', '--all')
    output = git(directory, 'diff', '--cached', '--name-status', '--no-renames', '-z', limit=128 * 1024)
    parts, result = output.split(b'\x00'), []
    for index in range(0, len(parts) - 1, 2):
        status, path = parts[index].decode(), parts[index + 1].decode('utf-8')
        if status not in ('A', 'M', 'D') or not allowed_path(path, permitted):
            raise LocalFailure('invalid_result')
        result.append({'path': path, 'change': {'A': 'added', 'M': 'modified', 'D': 'deleted'}[status]})
    if not result:
        raise LocalFailure('no_changes')
    if len(result) > 200:
        raise LocalFailure('invalid_result')
    patch = git(directory, 'diff', '--cached', '--no-ext-diff', '--no-textconv', '--no-renames', '--full-index', limit=PATCH_LIMIT)
    if b'Binary files ' in patch or b'GIT binary patch' in patch or b'\x00' in patch:
        raise LocalFailure('invalid_result')
    patch.decode('utf-8')
    return patch, result
