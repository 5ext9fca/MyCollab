import hashlib
import unittest

from backend.agent_bridge.code_protocol import relative_path, repository_key, validate_manifest, validate_report, verify_bytes
from backend.agent_bridge.protocol import ProtocolError


class CodeProtocolTests(unittest.TestCase):
    def test_repository_identifiers_are_not_paths_or_commands(self):
        for key in ('../repo', '/tmp/repo', 'repo;ls', 'https://example.com', '', 'a' * 65):
            with self.assertRaises(ProtocolError):
                repository_key(key)
        self.assertEqual(repository_key('rules-v1'), 'rules-v1')

    def test_paths_reject_traversal_and_credential_directories(self):
        for path in ('../file', 'src/../file', '/file', 'src//file', '.git/config', '.ssh/key', 'C:/file', 'src\\file'):
            with self.assertRaises(ProtocolError):
                relative_path(path)
        self.assertEqual(relative_path('src/rules.py'), 'src/rules.py')

    def test_report_does_not_claim_failure_passed(self):
        report = {'schema_version': 1, 'base_commit': 'a' * 40, 'summary': '实现规则',
            'changed_files': [{'path': 'rules.py', 'change': 'modified'}], 'source': 'local_runner',
            'verification': [{'id': 'unit', 'label': '单元测试', 'status': 'passed', 'exit_code': 1, 'duration_ms': 10}]}
        with self.assertRaises(ProtocolError):
            validate_report(report)
        report['verification'][0]['status'] = 'failed'
        validate_report(report)
        report['verification'][0]['command'] = '任意命令'
        with self.assertRaises(ProtocolError):
            validate_report(report)

    def test_delivery_checks_size_and_hash(self):
        data = b'diff --git a/rules.py b/rules.py\n'
        manifest = {'base_commit': 'a' * 40, 'patch_size': len(data), 'patch_sha256': hashlib.sha256(data).hexdigest(), 'report_size': 2, 'report_sha256': hashlib.sha256(b'{}').hexdigest()}
        validate_manifest(manifest)
        verify_bytes(data, 'patch', manifest)
        with self.assertRaises(ProtocolError):
            verify_bytes(data + b'changed', 'patch', manifest)
