"""为 CI 开发包记录来源、实际验收结果与安装文件摘要。"""
import hashlib
import json
import os
from pathlib import Path


def record(directory, environment):
    files = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in {'.exe', '.dmg', '.zip'}:
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            files.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()})
    if not files:
        raise RuntimeError('没有可记录的开发安装文件。')
    allowed = {'success', 'failure', 'cancelled', 'skipped'}
    def outcome(key):
        value = environment.get(key, '')
        return value if value in allowed else 'not_run'
    report = {
        'official_release': False,
        'build_commit': environment.get('GITHUB_SHA', ''),
        'pull_request_head': environment.get('VALIDATION_PR_HEAD', ''),
        'run_id': environment.get('GITHUB_RUN_ID', ''),
        'target': environment.get('VALIDATION_TARGET', ''),
        'packaged_gui': outcome('VALIDATION_PACKAGED_GUI'),
        'installed_gui_and_uninstall': outcome('VALIDATION_INSTALLED_GUI'),
        'files': files,
    }
    destination = directory / 'development-validation.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('仅供 CI 记录工作流验证结果。')
    record(Path(__file__).resolve().parents[1] / 'build/electron', os.environ)
