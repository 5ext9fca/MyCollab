"""代码成果的有界协议；不执行补丁或验证命令。"""
import hashlib
import re
from pathlib import PurePosixPath

from .protocol import ProtocolError, bounded_json, fields, text

CODE_KIND = 'code_implement'
PATCH_LIMIT = 2 * 1024 * 1024
REPORT_LIMIT = 128 * 1024
KEY = re.compile(r'[A-Za-z0-9_-]{1,64}')
SHA = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'(?:[a-f0-9]{40}|[a-f0-9]{64})')


def repository_key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise ProtocolError('仓库标识只能包含 1–64 位字母、数字、下划线或短横线。')
    return value


def relative_path(value):
    text(value, 500, True)
    path = PurePosixPath(value)
    if '"' in value or value.startswith('/') or '\\' in value or ':' in value or any(ord(c) < 32 for c in value) or any(p in ('', '.', '..') for p in value.split('/')) or str(path) != value:
        raise ProtocolError('变更路径必须是规范的仓库相对路径。')
    if any(p.lower() in ('.git', '.ssh', '.aws', '.opencode') for p in path.parts):
        raise ProtocolError('不得交付仓库元数据、认证目录或 Agent 配置。')
    return value


def validate_manifest(value):
    bounded_json(value, 4096)
    fields(value, ('base_commit', 'patch_sha256', 'patch_size', 'report_sha256', 'report_size'))
    if not isinstance(value['base_commit'], str) or not COMMIT.fullmatch(value['base_commit']):
        raise ProtocolError('基线提交无效。')
    for kind, limit in (('patch', PATCH_LIMIT), ('report', REPORT_LIMIT)):
        if not isinstance(value[kind + '_sha256'], str) or not SHA.fullmatch(value[kind + '_sha256']):
            raise ProtocolError('成果摘要无效。')
        if type(value[kind + '_size']) is not int or not 0 < value[kind + '_size'] <= limit:
            raise ProtocolError('成果大小超出限制。')
    return value


def validate_report(value):
    bounded_json(value, REPORT_LIMIT)
    fields(value, ('schema_version', 'base_commit', 'summary', 'changed_files', 'verification', 'source'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['source'] != 'local_runner':
        raise ProtocolError('报告版本或来源无效。')
    if not isinstance(value['base_commit'], str) or not COMMIT.fullmatch(value['base_commit']):
        raise ProtocolError('报告基线无效。')
    text(value['summary'], 10000, True)
    changed = value['changed_files']
    if not isinstance(changed, list) or not 1 <= len(changed) <= 200:
        raise ProtocolError('补丁需包含 1–200 个变更文件。')
    paths = set()
    for item in changed:
        fields(item, ('path', 'change'))
        relative_path(item['path'])
        if item['path'] in paths or item['change'] not in ('added', 'modified', 'deleted'):
            raise ProtocolError('变更文件重复或类型无效。')
        paths.add(item['path'])
    checks = value['verification']
    if not isinstance(checks, list) or len(checks) > 20:
        raise ProtocolError('最多记录 20 项本地验证。')
    ids = set()
    for check in checks:
        fields(check, ('id', 'label', 'status', 'exit_code', 'duration_ms'))
        repository_key(check['id'])
        text(check['label'], 200, True)
        if check['id'] in ids or check['status'] not in ('passed', 'failed', 'timeout', 'not_run'):
            raise ProtocolError('验证编号重复或状态无效。')
        ids.add(check['id'])
        code = check['exit_code']
        if code is not None and (type(code) is not int or not -255 <= code <= 255):
            raise ProtocolError('验证退出码无效。')
        if check['status'] == 'passed' and code != 0 or check['status'] == 'failed' and (code is None or code == 0) or check['status'] in ('timeout', 'not_run') and code is not None:
            raise ProtocolError('验证状态与真实退出码不一致。')
        if type(check['duration_ms']) is not int or not 0 <= check['duration_ms'] <= 1800000:
            raise ProtocolError('验证时长无效。')
    return value


def verify_bytes(data, kind, manifest):
    limit = PATCH_LIMIT if kind == 'patch' else REPORT_LIMIT
    if not 0 < len(data) <= limit or len(data) != manifest[kind + '_size'] or hashlib.sha256(data).hexdigest() != manifest[kind + '_sha256']:
        raise ProtocolError('成果内容与已确认清单不一致。')
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ProtocolError('代码成果必须为 UTF-8 文本。') from exc
    if '\x00' in content:
        raise ProtocolError('代码成果不能包含二进制内容。')
    return content


def validate_patch(content, report):
    headers = [line for line in content.splitlines() if line.startswith('diff --git ')]
    expected = [f"diff --git a/{item['path']} b/{item['path']}" for item in report['changed_files']]
    if not content.startswith('diff --git ') or len(headers) != len(expected) or set(headers) != set(expected):
        raise ProtocolError('补丁路径与报告变更清单不一致。')
    for line in content.splitlines():
        if line.startswith(('new file mode ', 'old mode ', 'new mode ', 'deleted file mode ')) and line.rsplit(' ', 1)[-1] not in ('100644', '100755'):
            raise ProtocolError('补丁只允许普通代码文件。')
        if line.startswith(('GIT binary patch', 'Binary files ')):
            raise ProtocolError('不接受二进制补丁。')
    return content
