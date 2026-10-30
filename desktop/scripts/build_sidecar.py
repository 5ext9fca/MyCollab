"""使用本机 Python 3.13 构建独立 Runner；不跨系统伪造二进制。"""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--electron', action='store_true', help='为 Electron 构建当前系统与架构的 Runner')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
if sys.version_info[:2] != (3, 13):
    raise SystemExit('桌面 Runner 构建要求 Python 3.13。')
arch = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(platform.machine().lower())
if sys.platform == 'darwin' and arch in ('arm64', 'x64'):
    target = f'mac-{arch}'
    filename = 'mycollab-runner'
elif args.electron and sys.platform == 'win32' and arch == 'x64':
    target, filename = 'win-x64', 'mycollab-runner.exe'
else:
    raise SystemExit('目标仅支持原生 macOS arm64/x64 或 Windows x64（--electron）。')
dist = root / 'desktop/build/runner' / target if args.electron else root / 'desktop/build/dist'
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
    '--name', 'mycollab-runner', '--paths', str(root), '--distpath', str(dist),
    '--workpath', str(root / 'desktop/build/work' / target), '--specpath', str(root / 'desktop/build'),
    str(root / 'desktop/scripts/runner_entry.py')], check=True, cwd=root)
if not (dist / filename).is_file():
    raise SystemExit('未生成预期架构的 Runner。')
if not args.electron:
    # 保留迁移期间旧 macOS 伴侣的构建入口；新宿主不依赖 Rust。
    destination = root / 'desktop/src-tauri/binaries'
    destination.mkdir(parents=True, exist_ok=True)
    triple = 'aarch64-apple-darwin' if arch == 'arm64' else 'x86_64-apple-darwin'
    shutil.copy2(dist / filename, destination / f'mycollab-runner-{triple}')
print(f'已生成 {target} 独立 Runner：{dist / filename}')
