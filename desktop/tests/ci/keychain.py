"""仅供 GitHub 托管 macOS 验收：真实钥匙串，限定本次测试宿主。"""
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys


def security(*args):
    # 不在异常中输出参数：其中可能包含本次临时测试密钥。
    result = subprocess.run(['/usr/bin/security', *map(str, args)], capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'验收钥匙串操作失败：{args[0]}（{result.returncode}）')
    return result.stdout


@contextmanager
def isolated_keychain(directory):
    if sys.platform != 'darwin':
        yield
        return
    if not (os.environ.get('CI') == 'true' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'):
        raise RuntimeError('临时钥匙串仅允许在 GitHub 托管 macOS 运行器中使用。')
    original_default = shlex.split(security('default-keychain', '-d', 'user'))
    original_search = shlex.split(security('list-keychains', '-d', 'user'))
    if len(original_default) != 1:
        raise RuntimeError('无法确定原默认钥匙串。')
    keychain = Path(directory) / 'desktop-acceptance.keychain-db'
    password = secrets.token_urlsafe(32)
    security('create-keychain', '-p', password, keychain)
    try:
        security('set-keychain-settings', '-lut', '600', keychain)
        security('unlock-keychain', '-p', password, keychain)
        security('list-keychains', '-d', 'user', '-s', keychain)
        security('default-keychain', '-d', 'user', '-s', keychain)
        yield
    finally:
        # 即使其中一步恢复失败，也继续尝试其余清理。
        errors = []
        for args in [('default-keychain', '-d', 'user', '-s', *original_default),
                     ('list-keychains', '-d', 'user', '-s', *original_search),
                     ('delete-keychain', keychain)]:
            try:
                security(*args)
            except Exception as error:
                errors.append(error)
        if errors:
            raise RuntimeError('验收钥匙串清理失败。') from errors[0]
