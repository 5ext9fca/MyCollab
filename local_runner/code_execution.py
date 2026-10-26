"""代码委派本地交接：补丁与报告经人审查后才上传。"""
import hashlib
import json
from pathlib import Path
import re
import shutil
from uuid import UUID

from backend.agent_bridge.code_protocol import validate_manifest, validate_report, validate_patch, verify_bytes, PATCH_LIMIT, REPORT_LIMIT
from . import code_workspace, opencode_code
from .code_verification import run_checks
from .images import output_directory, save_state, retry
from .opencode import Cancelled, LocalFailure


def directory_for(config, request_id, create=False):
    return output_directory({'image_output_dir': config['code_output_dir']}, request_id, create=create)


def public_text(value):
    # 本地工具路径只保存在本机，不进入结构化交付报告。
    return re.sub(r'(?:/(?:Users|home|private|var|tmp|etc|opt|Volumes|mnt)/[^\s`"<>]+|[A-Za-z]:[\\/][^\s`"<>]+)', '[本地路径]', value)


def execute_code(client, request, config):
    endpoint = f"requests/{str(UUID(request['id']))}/"
    attempt = {'attempt_id': str(UUID(request['attempt_id']))}
    def heartbeat():
        try:
            return client.post(endpoint + 'heartbeat/', attempt)['status'] == 'running'
        except Exception:
            return False
    try:
        repository = code_workspace.configuration(config, request['input']['repository_key'])
        directory = directory_for(config, request['id'], create=True)
        workspace = directory / 'workspace'
        base = code_workspace.prepare(repository, workspace)
        if not heartbeat():
            raise Cancelled()
        summary = opencode_code.run(request, workspace, repository['writable_paths'], model=config.get('code_model', config.get('model', '')),
            executable=config.get('opencode', 'opencode'), heartbeat=heartbeat)
        patch, files = code_workspace.changes(workspace, repository['writable_paths'])
        # 测试输出不污染补丁，也不共享原仓库 Git 元数据。
        verification_workspace = directory / 'verification'
        shutil.copytree(workspace, verification_workspace, ignore=shutil.ignore_patterns('.git'))
        checks = run_checks(repository['verification'], verification_workspace, directory / 'logs', heartbeat=heartbeat)
        if code_workspace.changes(workspace, repository['writable_paths'])[0] != patch:
            raise LocalFailure('invalid_result')
        for check in checks:
            check['label'] = public_text(check['label'])
        report = validate_report({'schema_version': 1, 'source': 'local_runner', 'base_commit': base,
            'summary': public_text(summary), 'changed_files': files, 'verification': checks})
        validate_patch(patch.decode('utf-8'), report)
        report_data = json.dumps(report, ensure_ascii=False, sort_keys=True).encode()
        manifest = validate_manifest({'base_commit': base, 'patch_sha256': hashlib.sha256(patch).hexdigest(),
            'patch_size': len(patch), 'report_sha256': hashlib.sha256(report_data).hexdigest(), 'report_size': len(report_data)})
        for name, data in (('changes.patch', patch), ('report.json', report_data)):
            path = directory / name
            path.write_bytes(data); path.chmod(0o600)
        state = {'server': client.url, 'request_id': request['id'], 'attempt_id': request['attempt_id'], 'manifest': manifest}
        save_state(directory, state)
        (directory / 'REVIEW.txt').write_text('请人工查看 changes.patch 与 report.json。报告是本地验证证据，不是服务器独立验证。\n验证原始输出在 logs/，不会上传。没有验证项表示未配置验证。\n确认后运行 --publish-code 请求UUID；仅发布本次已有成果，不会重新执行模型。\n', encoding='utf-8')
        (directory / 'REVIEW.txt').chmod(0o600)
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
        print('未产生代码差异，请人工检查任务与基线。' if code == 'no_changes' else '代码执行未完成；未自动重新生成。错误类别：' + code, flush=True)
        return
    try:
        retry(lambda: client.post(endpoint + 'code-manifest/', {**attempt, 'manifest': manifest}))
    except Exception:
        print('成果清单未确认回传；仅在执行租约仍有效时可重传，未重新执行模型。', flush=True)
    print(f'请在本机检查 {directory / "changes.patch"} 与 report.json。\n确认后运行 --publish-code {request["id"]}；当前尚未上传成果正文。', flush=True)


def publish(client, config, request_id):
    directory = directory_for(config, request_id)
    path = directory / 'state.json'
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('本地执行记录无效。')
    state = json.loads(path.read_text())
    if state['server'] != client.url or state['request_id'] != str(UUID(request_id)):
        raise ValueError('执行与服务器不匹配。')
    manifest = validate_manifest(state['manifest'])
    values = {}
    for key, name, limit in (('patch', 'changes.patch', PATCH_LIMIT), ('report', 'report.json', REPORT_LIMIT)):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            raise ValueError('本地成果文件无效。')
        values[key] = path.read_bytes()
        verify_bytes(values[key], key, manifest)
    report = validate_report(json.loads(values['report']))
    validate_patch(values['patch'].decode('utf-8'), report)
    if report['base_commit'] != manifest['base_commit']:
        raise ValueError('报告基线不一致。')
    endpoint = f'requests/{str(UUID(request_id))}/'
    attempt = {'attempt_id': str(UUID(state['attempt_id']))}
    retry(lambda: client.post(endpoint + 'code-manifest/', {**attempt, 'manifest': manifest}))
    retry(lambda: client.publish_code(endpoint + 'code-publish/', attempt['attempt_id'], values['patch'], values['report']))
    print('代码成果已发布；请回到 Mission 人工检查、填写验证说明并提交。', flush=True)
