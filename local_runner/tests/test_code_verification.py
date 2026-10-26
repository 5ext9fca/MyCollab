from pathlib import Path
import sys
import tempfile
import unittest

from local_runner.code_verification import run_checks
from local_runner.opencode import Cancelled
from local_runner.opencode_code import configuration


class VerificationTests(unittest.TestCase):
    def test_real_exit_codes_timeout_and_missing_tool(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checks = [{'id': 'pass', 'label': '通过', 'argv': [sys.executable, '-c', 'print("ok")']},
                {'id': 'fail', 'label': '失败', 'argv': [sys.executable, '-c', 'raise SystemExit(3)']},
                {'id': 'timeout', 'label': '超时', 'argv': [sys.executable, '-c', 'import time; time.sleep(10)'], 'timeout': 1},
                {'id': 'missing', 'label': '未运行', 'argv': ['/nonexistent/mycollab-check']}]
            result = run_checks(checks, root, root / 'logs')
            self.assertEqual([r['status'] for r in result], ['passed', 'failed', 'timeout', 'not_run'])
            self.assertEqual([r['exit_code'] for r in result], [0, 3, None, None])
            self.assertIn('ok', (root / 'logs/pass.log').read_text())

    def test_cancel_prevents_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(Cancelled):
                run_checks([{'id': 'unit', 'label': '单测', 'argv': [sys.executable, '-c', 'print(1)']}], root, root / 'logs', heartbeat=lambda: False)

    def test_agent_does_not_receive_shell_or_external_authority(self):
        value = configuration(['src'])
        rules = value['agents']['mycollab-code']['permissions']
        self.assertEqual(rules[0], {'action': '*', 'resource': '*', 'effect': 'deny'})
        self.assertFalse(any(r['action'] == 'shell' and r['effect'] == 'allow' for r in rules))
        self.assertIn({'action': 'tool.use', 'resource': 'external_directory:*', 'effect': 'deny'}, value['policies'])
        self.assertFalse(value['formatter'])
