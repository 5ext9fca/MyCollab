"""真实 HTTP/子进程断线恢复；模型使用本机假 CLI，不调用供应商。"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

from local_runner.tests.fixture_cli import model_fixture
from local_runner.parent_process import ParentProcess


class DeliveryIntegrationTests(unittest.TestCase):
    def test_restart_after_server_commit_lost_ack_never_regenerates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_count = root / 'model-count'
            cli, model = model_fixture(root, 'complete')
            claimed, results = [], []
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass
                def do_POST(self):
                    data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    response = None
                    if self.path.endswith('/claim/') and not claimed:
                        claimed.append(True)
                        response = {'id':'request', 'attempt_id':'attempt', 'schema_version':1, 'kind':'design_polish',
                                    'input':{}, 'lease_expires_at':(datetime.now(timezone.utc)+timedelta(seconds=180)).isoformat()}
                    elif self.path.endswith('/result/'):
                        results.append(data)
                        if len(results) == 1:
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.connection.close()
                            return
                        response = {'status':'succeeded'}
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode())
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                config = root / 'config.json'
                config.write_text(json.dumps({'server':f'http://127.0.0.1:{server.server_port}', 'device_token':'test', 'model':model, 'opencode':cli}))
                config.chmod(0o600)
                binary = os.environ.get('MYCOLLAB_TEST_RUNNER_BINARY')
                command = [binary] if binary else [sys.executable, '-m', 'local_runner']
                for _ in range(2):
                    result = subprocess.run(command + ['--config', str(config), '--once'], cwd=root if binary else None, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(model_count.read_text(), '1')
                self.assertEqual(len(results), 2)
                self.assertEqual(results[0], results[1])
                self.assertEqual(list(root.glob('runner-state/*/result-*.json')), [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_desktop_parent_exit_terminates_running_model(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'started'
            stopped = root / 'stopped'
            cli, model = model_fixture(root, 'wait')
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_POST(self):
                    self.rfile.read(int(self.headers['Content-Length']))
                    self.send_response(200); self.end_headers()
                    self.wfile.write(json.dumps({'id':'request','attempt_id':'attempt','schema_version':1,'kind':'design_polish','input':{},
                        'lease_expires_at':(datetime.now(timezone.utc)+timedelta(seconds=180)).isoformat()}).encode())
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            runner = None
            try:
                config = root / 'config.json'
                config.write_text(json.dumps({'server':f'http://127.0.0.1:{server.server_port}','device_token':'test','model':model,'opencode':cli})); config.chmod(0o600)
                binary = os.environ.get('MYCOLLAB_TEST_RUNNER_BINARY')
                command = [binary] if binary else [sys.executable, '-m', 'local_runner']
                runner = subprocess.Popen(command + ['--config',str(config),'--parent-pid',str(parent.pid)], cwd=root if binary else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                deadline = time.monotonic() + 20
                while not marker.exists():
                    self.assertIsNone(runner.poll())
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.05)
                model_process = ParentProcess(int(marker.read_text()))
                try:
                    parent.terminate(); parent.wait(timeout=5)
                    self.assertEqual(runner.wait(timeout=10), 130)
                    deadline = time.monotonic() + 5
                    while model_process.alive() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertFalse(model_process.alive(), '宿主退出后不能遗留模型进程')
                    if os.name == 'posix':
                        self.assertTrue(stopped.exists())
                finally:
                    model_process.close()
            finally:
                if runner:
                    if runner.poll() is None: runner.terminate(); runner.wait(timeout=10)
                    runner.communicate()
                if parent.poll() is None: parent.terminate(); parent.wait(timeout=5)
                server.shutdown(); server.server_close(); thread.join()
