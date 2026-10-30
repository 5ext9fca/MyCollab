"""匿名管道凭据交接：只运行 CLI，不启动窗口或模型。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PrivateHandoffTests(unittest.TestCase):
    def invoke(self, directory, raw):
        path = Path(directory) / '中文 状态' / 'runner.json'
        process = subprocess.run([sys.executable, '-m', 'local_runner', '--config', str(path),
            '--config-stdin', '--status'], input=raw, capture_output=True, timeout=10)
        self.assertFalse(path.exists(), '不得写入明文配置文件')
        self.assertNotIn(b'private-device-secret', process.stdout + process.stderr)
        return process

    def test_status_uses_pipe_without_plaintext_file_or_secret_output(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = json.dumps({'server': 'https://example.com', 'device_token': 'private-device-secret',
                              'model': 'provider/model'}).encode() + b'\n'
            process = self.invoke(directory, raw)
            self.assertEqual(process.returncode, 0, process.stderr.decode())
            self.assertEqual(json.loads(process.stdout)['state'], 'stopped')
            for path in Path(directory).rglob('*'):
                if path.is_file():
                    self.assertNotIn(b'private-device-secret', path.read_bytes())

    def test_bounded_malformed_or_missing_pipe_input_is_rejected_without_echo(self):
        for raw in [b'', b'{private-device-secret}\n', b'{}', b'private-device-secret' * 2000 + b'\n',
                    b'[]\n', b'\xff\n']:
            with self.subTest(raw_length=len(raw)), tempfile.TemporaryDirectory() as directory:
                process = self.invoke(directory, raw)
                self.assertEqual(process.returncode, 2)
                self.assertNotIn(b'Traceback', process.stderr)
