"""真实 Runner 管道关闭停止，不打开界面或执行模型。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest


class ControlPipeTests(unittest.TestCase):
    def test_stop_byte_in_same_write_as_config_is_not_lost(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'server': 'http://127.0.0.1:9', 'device_token': 'private-secret', 'model': 'fixture/model'}
            process = subprocess.Popen([sys.executable, '-m', 'local_runner', '--config', str(Path(directory) / 'runner.json'),
                '--config-stdin', '--control-stdin'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                process.stdin.write(json.dumps(config).encode() + b'\nstop\n')
                process.stdin.flush()
                # 保持管道打开，证明是停止字节生效而非 EOF 偶然触发。
                self.assertEqual(process.wait(timeout=5), 130)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_pipe_eof_stops_idle_runner_and_releases_device_lock(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.send_response(204)
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'runner.json'
                config = {'server': f'http://127.0.0.1:{server.server_port}', 'device_token': 'private-secret', 'model': 'fixture/model'}
                process = subprocess.Popen([sys.executable, '-m', 'local_runner', '--config', str(path),
                    '--config-stdin', '--control-stdin'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    process.stdin.write(json.dumps(config).encode() + b'\n')
                    process.stdin.flush()
                    deadline = time.monotonic() + 10
                    status = None
                    while time.monotonic() < deadline:
                        files = list(Path(directory).glob('runner-state/*/status.json'))
                        if files:
                            status = files[0]
                            if json.loads(status.read_text())['state'] == 'idle':
                                break
                        time.sleep(0.05)
                    self.assertIsNotNone(status)
                    self.assertEqual(json.loads(status.read_text())['state'], 'idle')
                    process.stdin.close()
                    process.stdin = None
                    stdout, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 130)
                    self.assertNotIn(b'private-secret', stdout + stderr)
                    self.assertEqual(json.loads(status.read_text())['state'], 'stopped')
                    from local_runner.state import StateStore
                    with StateStore(path, config['server'], config['device_token']).lock():
                        pass
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
