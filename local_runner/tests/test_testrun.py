"""使用假服务验证启动脚本，不连接数据库或模型。"""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class TestRunTests(unittest.TestCase):
    def test_runner_start_skip_exit_and_cleanup(self):
        for mode in ("missing", "running", "failed"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script = Path(__file__).resolve().parents[2] / "testrun.sh"
                config = root / "runner.json"
                if mode != "missing":
                    config.write_text("{}")
                (root / "testrun.sh").write_text(script.read_text().replace('runner_config="$HOME/.config/MyCollab/mycollab-runner.json"', f'runner_config="{config}"'))
                binary = root / "bin"
                binary.mkdir()
                (root / "backend/.venv/bin").mkdir(parents=True)
                (root / "frontend/node_modules/.bin").mkdir(parents=True)
                (root / "frontend/node_modules/.bin/vite").touch(mode=0o755)
                fake = root / "fake"
                fake.write_text(f'''#!{sys.executable}
import os, signal, sys, time
from pathlib import Path
args = sys.argv[1:]
kind = "runner" if "local_runner" in args else "backend" if "runserver" in args else "frontend" if any("vite.js" in arg for arg in args) else ""
if not kind:
    sys.exit(0)
root = Path({str(root)!r})
(root / (kind + ".pid")).write_text(str(os.getpid()))
def stop(*args):
    (root / (kind + ".stopped")).touch()
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
if kind == "runner" and {mode!r} == "failed":
    sys.exit(2)
while True:
    time.sleep(0.05)
''')
                fake.chmod(0o755)
                for tool in ("docker", "node", "npm", "curl"):
                    (binary / tool).symlink_to(fake)
                (root / "backend/.venv/bin/python").symlink_to(fake)
                env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
                output = root / "output"
                with output.open("w") as log:
                    process = subprocess.Popen([shutil.which("bash"), str(root / "testrun.sh")], env=env, stdout=log, stderr=log, start_new_session=True)
                    try:
                        expected = "跳过自动启动" if mode == "missing" else "LocalRunner 已退出" if mode == "failed" else "测试环境已就绪"
                        deadline = time.monotonic() + 60
                        while expected not in output.read_text(errors="replace") or (mode == "running" and not (root / "runner.pid").exists()):
                            self.assertIsNone(process.poll(), output.read_text(errors="replace"))
                            self.assertLess(time.monotonic(), deadline, output.read_text(errors="replace"))
                            time.sleep(0.05)
                        self.assertIsNone(process.poll())
                        process.send_signal(signal.SIGINT)
                        self.assertEqual(process.wait(timeout=20), 130)
                        for kind in ("backend", "frontend") + (("runner",) if mode == "running" else ()):
                            self.assertTrue((root / (kind + ".stopped")).exists(), output.read_text(errors="replace"))
                        if mode == "missing":
                            self.assertFalse((root / "runner.pid").exists())
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
