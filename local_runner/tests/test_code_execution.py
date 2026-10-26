import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from local_runner.code_execution import execute_code, publish, directory_for
from local_runner.code_workspace import git
from local_runner.opencode_code import run


class CodeExecutionRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        (self.source / 'rules.py').write_text('VALUE = 1\n')
        git(self.source, 'init', '-q'); git(self.source, 'add', '--all')
        git(self.source, '-c', 'user.name=Test', '-c', 'user.email=test@invalid', 'commit', '-qm', '基线')
        self.config = {'code_output_dir': str(self.root / 'outputs'), 'model': 'test/model', 'repositories': {'demo': {
            'path': str(self.source), 'writable_paths': ['rules.py'], 'verification': [{'id': 'unit', 'label': '单测',
                'argv': [sys.executable, '-c', 'from rules import VALUE; assert VALUE == 2'], 'timeout': 10}]}}}
        self.client = Mock(url='https://example.com'); self.client.post.return_value = {'status': 'running'}
        self.request = {'id': str(uuid4()), 'attempt_id': str(uuid4()), 'schema_version': 1, 'kind': 'code_implement',
            'input': {'repository_key': 'demo', 'instructions': '实现规则'}}

    def model(self, request, directory, paths, **kwargs):
        (directory / 'rules.py').write_text('VALUE = 2\n')
        return '修改规则；本机路径 /Users/example/private 已省略。'

    @patch('local_runner.code_execution.opencode_code.run')
    @patch('local_runner.images.time.sleep')
    def test_explicit_publish_and_same_bytes_retry_without_model_repeat(self, sleep, model):
        model.side_effect = self.model
        execute_code(self.client, self.request, self.config)
        self.client.publish_code.assert_not_called()
        directory = directory_for(self.config, self.request['id'])
        report = json.loads((directory / 'report.json').read_text())
        self.assertEqual(report['verification'][0]['status'], 'passed')
        self.assertNotIn('/Users/', report['summary'])
        self.assertEqual((self.source / 'rules.py').read_text(), 'VALUE = 1\n')
        self.client.publish_code.side_effect = [OSError(), {}]
        publish(self.client, self.config, self.request['id'])
        self.assertEqual(model.call_count, 1)
        self.assertEqual(self.client.publish_code.call_args_list[0], self.client.publish_code.call_args_list[1])

    @patch('local_runner.code_execution.opencode_code.run')
    def test_failed_check_is_reported_and_tampered_patch_cannot_publish(self, model):
        model.side_effect = self.model
        self.config['repositories']['demo']['verification'][0]['argv'] = [sys.executable, '-c', 'raise SystemExit(7)']
        execute_code(self.client, self.request, self.config)
        directory = directory_for(self.config, self.request['id'])
        report = json.loads((directory / 'report.json').read_text())
        self.assertEqual(report['verification'][0]['status'], 'failed')
        self.assertEqual(report['verification'][0]['exit_code'], 7)
        (directory / 'changes.patch').write_text('forged')
        with self.assertRaises(ValueError):
            publish(self.client, self.config, self.request['id'])
        self.client.publish_code.assert_not_called()

    @patch('local_runner.code_execution.opencode_code.run')
    def test_unknown_repository_never_calls_model(self, model):
        self.request['input']['repository_key'] = 'unknown'
        execute_code(self.client, self.request, self.config)
        model.assert_not_called()
        self.assertEqual(self.client.post.call_args.args[1]['error'], 'local_configuration')

    @patch('local_runner.opencode_code.subprocess.run')
    @patch('local_runner.opencode_code.subprocess.Popen')
    def test_private_cwd_is_also_explicit_in_environment(self, popen, version):
        version.return_value = Mock(returncode=0, stdout='opencode v2.1.3')
        process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(), poll=Mock(return_value=0), wait=Mock(return_value=0))
        popen.return_value = process
        run(self.request, self.source, ['rules.py'], model='test/model')
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs['cwd'], self.source.resolve())
        self.assertEqual(kwargs['env']['PWD'], str(self.source.resolve()))
        self.assertNotIn('OLDPWD', kwargs['env'])
