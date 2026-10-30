"""仅在 Windows CI 中安装开发 NSIS、验收安装副本并卸载。"""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    if sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('此安装验收仅供 GitHub Windows 临时运行器。')
    root = Path(__file__).resolve().parents[3]
    installers = list((root / 'desktop/build/electron').glob('*-win-x64-development.exe'))
    if len(installers) != 1:
        raise SystemExit('必须只有一个 Windows 开发安装包。')
    with TemporaryDirectory(prefix='mycollab-install-') as temporary:
        destination = Path(temporary) / '中文 安装路径'
        # NSIS 的 /D 必须放在最后且不加引号；不经过 shell 解释。
        command = subprocess.list2cmdline([str(installers[0]), '/S', '/currentuser'])
        try:
            subprocess.run(command + ' /D=' + str(destination), check=True, timeout=180)
            app = destination / 'MyCollab.exe'
            runner = destination / 'resources/runner/mycollab-runner.exe'
            if not app.is_file() or not runner.is_file():
                raise RuntimeError('安装器未在指定目录生成应用与 Runner。')
            subprocess.run([sys.executable, str(root / 'desktop/tests/ci/check_gui.py'),
                            '--app', str(app), '--artifact-group', 'installed'], check=True, timeout=270)
        finally:
            uninstallers = list(destination.glob('Uninstall*.exe'))
            if len(uninstallers) == 1:
                command = subprocess.list2cmdline([str(uninstallers[0]), '/S', '/currentuser'])
                subprocess.run(command + ' _?=' + str(destination), check=True, timeout=180)
        if (destination / 'MyCollab.exe').exists():
            raise RuntimeError('卸载后应用可执行文件仍存在。')
    (root / 'desktop/build/windows-install-validation.json').write_text(
        json.dumps({'installer': installers[0].name, 'silent_install': True,
                    'installed_gui': True, 'silent_uninstall': True,
                    'native_wizard_interaction': False, 'official_release': False}, indent=2) + '\n',
        encoding='utf-8',
    )


if __name__ == '__main__':
    main()
