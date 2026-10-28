"""非 GUI 验证独立 Runner：管道配置、空领取、状态与私有目录。"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

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
                             'device_token': 'smoke-device-secret', 'model': 'fixture/model'}).encode() + b'\n'
        command = [str(executable), '--config', str(config), '--config-stdin', '--parent-pid', str(os.getpid())]
        for mode in ['--once', '--status']:
            result = subprocess.run(command + [mode], input=payload, capture_output=True, timeout=30)
            if result.returncode:
                raise SystemExit('独立 Runner 验证失败；请检查产物依赖、权限和平台。')
            assert b'smoke-device-secret' not in result.stdout + result.stderr
            if mode == '--status':
                snapshot = json.loads(result.stdout)
                assert snapshot['state'] == 'stopped' and snapshot['pending_results'] == 0
        assert claims == [True]
        assert not config.exists()
        for path in Path(directory).rglob('*'):
            if path.is_file():
                assert b'smoke-device-secret' not in path.read_bytes()
    print('独立 Runner 非 GUI 验证通过：匿名管道、中文路径、空领取、状态、无明文令牌。')
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
