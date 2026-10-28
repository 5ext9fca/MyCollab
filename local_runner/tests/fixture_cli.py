"""测试夹具构建入口；Windows 必须提供原生假 CLI，不用 shell 绕过 Job。"""
import json
import os
from pathlib import Path
import sys


def model_fixture(root, mode):
    source = Path(__file__).parent / 'fixtures/opencode.py'
    if os.name == 'nt':
        executable = os.environ.get('MYCOLLAB_TEST_OPENCODE_BINARY')
        if not executable or not Path(executable).is_file():
            raise RuntimeError('Windows 集成测试需要先打包假 CLI 并设置 MYCOLLAB_TEST_OPENCODE_BINARY。')
        cli = Path(executable).resolve()
    else:
        cli = root / 'opencode'
        cli.write_text(f'#!{sys.executable}\n' + source.read_text(encoding='utf-8'), encoding='utf-8')
        cli.chmod(0o700)
    settings = root / '模型 配置.json'
    settings.write_text(json.dumps({'mode': mode, 'counter': str(root / 'model-count'),
        'started': str(root / 'started'), 'stopped': str(root / 'stopped')}), encoding='utf-8')
    return str(cli), str(settings)
