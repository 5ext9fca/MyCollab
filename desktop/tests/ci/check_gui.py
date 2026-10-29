"""在 CI 临时 PostgreSQL 集群中运行真实桌面验收，不接触现有数据库。"""
import argparse
import os
from pathlib import Path
import shutil
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
    args = parser.parse_args()
    if args.app and not args.app.is_file():
        raise SystemExit('打包应用可执行文件不存在。')
    root = Path(__file__).resolve().parents[3]
    with TemporaryDirectory(prefix='mycollab-gui-db-') as temporary:
        data = Path(temporary) / 'data'
        subprocess.run([binaries['initdb'], '-D', str(data), '-U', 'postgres',
                        '--auth=trust', '--encoding=UTF8', '--locale=C'], check=True)
        control = [binaries['pg_ctl'], '-D', str(data)]
        subprocess.run([*control, '-l', str(Path(temporary) / 'postgres.log'),
                        '-o', '-h 127.0.0.1 -p 55439', '-w', 'start'], check=True)
        try:
            env = {**os.environ, 'MYCOLLAB_DESKTOP_TEST': '1',
                   'POSTGRES_DB': 'mycollab_desktop_gui', 'POSTGRES_USER': 'postgres',
                   'POSTGRES_PASSWORD': '', 'POSTGRES_HOST': '127.0.0.1',
                   'POSTGRES_PORT': '55439'}
            if args.app:
                env['MYCOLLAB_TEST_APP_BINARY'] = str(args.app.resolve())
            source_host = root / 'desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'
            with isolated_keychain(temporary, [source_host, args.app] if args.app else [source_host]):
                subprocess.run([sys.executable, 'manage.py', 'test', 'accounts.test_desktop',
                                '--noinput'], cwd=root / 'backend', env=env, check=True, timeout=240)
        finally:
            subprocess.run([*control, '-m', 'immediate', '-w', 'stop'], check=True)


if __name__ == '__main__':
    main()
