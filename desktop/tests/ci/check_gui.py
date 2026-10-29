"""在 CI 临时 PostgreSQL 集群中运行真实桌面验收，不接触现有数据库。"""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from keychain import isolated_keychain


def main():
    if os.environ.get('CI') != 'true':
        raise SystemExit('此入口仅供 CI；本机请使用 TECH_STACK 中的隔离 Django 命令。')
    binaries = {name: shutil.which(name) for name in ('initdb', 'pg_ctl')}
    if not all(binaries.values()):
        raise SystemExit('缺少 PostgreSQL 原生工具。')
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path)
    parser.add_argument('--artifact-group', choices=['packaged', 'installed'], default='packaged')
    args = parser.parse_args()
    if args.app and not args.app.is_file():
        raise SystemExit('打包应用可执行文件不存在。')
    root = Path(__file__).resolve().parents[3]
    with TemporaryDirectory(prefix='mycollab-gui-db-') as temporary:
        data = Path(temporary) / 'data'
        subprocess.run([binaries['initdb'], '-D', str(data), '-U', 'postgres',
                        '--auth=trust', '--encoding=UTF8', '--locale=C'], check=True)
        control = [binaries['pg_ctl'], '-D', str(data)]
        # Windows 运行器可能保留固定高位端口；让系统选择当前可绑定的端口。
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        log = Path(temporary) / 'postgres.log'
        try:
            subprocess.run([*control, '-l', str(log),
                            '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start'], check=True)
        except subprocess.CalledProcessError:
            if log.is_file():
                print(log.read_text(encoding='utf-8', errors='replace'), flush=True)
            subprocess.run([*control, '-m', 'immediate', '-w', 'stop'], check=False)
            raise
        try:
            env = {**os.environ, 'MYCOLLAB_DESKTOP_TEST': '1',
                   'POSTGRES_DB': 'mycollab_desktop_gui', 'POSTGRES_USER': 'postgres',
                   'POSTGRES_PASSWORD': '', 'POSTGRES_HOST': '127.0.0.1',
                   'POSTGRES_PORT': str(port)}
            if args.app:
                env['MYCOLLAB_TEST_APP_BINARY'] = str(args.app.resolve())
            # macOS 的两个宿主签名不同，分别在全新的系统钥匙串中运行。
            # 不预置加密材料，不让两个程序共享同名条目的访问控制。
            suites = ['migration', 'packaged'] if sys.platform == 'darwin' else ['packaged']
            for suite in suites:
                with isolated_keychain(temporary):
                    subprocess.run([sys.executable, 'manage.py', 'test', 'accounts.test_desktop',
                                    '--noinput'], cwd=root / 'backend',
                                   env={**env, 'MYCOLLAB_DESKTOP_TEST_SUITE': suite,
                                        'MYCOLLAB_DESKTOP_TEST_ARTIFACT_GROUP': f'ci-{args.artifact_group}'},
                                   check=True, timeout=240)
        finally:
            subprocess.run([*control, '-m', 'immediate', '-w', 'stop'], check=True)


if __name__ == '__main__':
    main()
