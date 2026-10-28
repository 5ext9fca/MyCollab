"""构建当前 macOS 架构的独立 Runner，不依赖用户安装 Python。"""
from pathlib import Path
import platform
import shutil
import subprocess
import sys
root = Path(__file__).resolve().parents[2]
if sys.version_info[:2] != (3, 13) or sys.platform != 'darwin':
    raise SystemExit('桌面 Runner 构建要求 macOS + Python 3.13。')
target = 'aarch64-apple-darwin' if platform.machine() == 'arm64' else 'x86_64-apple-darwin'
destination = root / 'desktop/src-tauri/binaries'
destination.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', 'mycollab-runner',
    '--paths', str(root), '--distpath', str(root/'desktop/build/dist'), '--workpath', str(root/'desktop/build/work'),
    '--specpath', str(root/'desktop/build'), str(root/'desktop/scripts/runner_entry.py')], check=True, cwd=root)
shutil.copy2(root/'desktop/build/dist/mycollab-runner', destination/f'mycollab-runner-{target}')
print('已生成当前架构的独立 Runner。')
