"""非 GUI 验证独立 Runner：管道配置、空领取、状态与私有目录。"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('executable', type=Path)
args = parser.parse_args()
executable = args.executable.resolve(strict=True)
claims = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path == '/api/agent-runner/claim/' and self.headers.get('Authorization') == 'Bearer smoke-device-secret':
            claims.append(True)
            self.send_response(204)
        else:
            self.send_response(403)
        self.end_headers()


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with tempfile.TemporaryDirectory(prefix='mycollab-runner-') as directory:
        config = Path(directory) / '中文 空格' / 'runner.json'
        payload = json.dumps({'server': f'http://127.0.0.1:{server.server_port}',
                             'device_token': 'smoke-device-secret', 'model': 'fixture/model',
                             'opencode': str(config.parent / 'missing-opencode')}).encode() + b'\n'
        command = [str(executable), '--config', str(config), '--config-stdin', '--parent-pid', str(os.getpid())]
        for mode in ['--once', '--status']:
            result = subprocess.run(command + [mode], input=payload, capture_output=True, timeout=30)
            if result.returncode:
                raise SystemExit('独立 Runner 验证失败；请检查产物依赖、权限和平台。')
            assert b'smoke-device-secret' not in result.stdout + result.stderr
            if mode == '--status':
                snapshot = json.loads(result.stdout)
                assert snapshot['state'] == 'stopped' and snapshot['pending_results'] == 0
        process = subprocess.Popen(command + ['--control-stdin', '--desktop-events'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.stdin.write(payload)
            process.stdin.flush()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                status = list(config.parent.glob('runner-state/*/status.json'))
                if status and json.loads(status[0].read_text())['state'] == 'idle':
                    break
                if process.poll() is not None:
                    raise SystemExit('Runner 在管道停止检查前退出。')
                time.sleep(0.05)
            else:
                raise SystemExit('Runner 未进入空闲状态。')
            competing = subprocess.run(command + ['--once'], input=payload, capture_output=True, timeout=15)
            assert competing.returncode != 0, '同一状态目录不允许两个 Runner 同时运行'
            assert b'smoke-device-secret' not in competing.stdout + competing.stderr
            process.stdin.close()
            process.stdin = None
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 130
            assert json.loads(stdout.splitlines()[0]) == {'event': 'ready'}
            assert b'smoke-device-secret' not in stdout + stderr
            assert json.loads(status[0].read_text())['state'] == 'stopped'
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        diagnostic = subprocess.Popen(command + ['--diagnose', '--control-stdin'], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            diagnostic.stdin.write(payload)
            diagnostic.stdin.flush()
            diagnostic.wait(timeout=30)
            stdout, stderr = diagnostic.communicate(timeout=5)
            assert diagnostic.returncode == 0
            checks = json.loads(stdout)
            assert checks['opencode'] == 'unavailable' and checks['server'] == 'unauthorized'
            assert b'smoke-device-secret' not in stdout + stderr
        finally:
            if diagnostic.poll() is None:
                diagnostic.kill()
                diagnostic.communicate(timeout=5)
        assert len(claims) >= 2
        assert not config.exists()
        for path in Path(directory).rglob('*'):
            if path.is_file():
                assert b'smoke-device-secret' not in path.read_bytes()
    print('独立 Runner 非 GUI 验证通过：匿名管道、中文路径、空领取、状态、管道关闭停止、无明文令牌。')
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
