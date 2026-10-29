"""验证无人值守钥匙串的环境限制、最小授权和异常恢复。"""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from keychain import isolated_keychain


class KeychainTests(unittest.TestCase):
    def test_local_mac_is_rejected_without_touching_keychain(self):
        with patch('keychain.sys.platform', 'darwin'), patch.dict(os.environ, {}, clear=True), patch('keychain.security') as call:
            with self.assertRaisesRegex(RuntimeError, 'GitHub 托管'):
                with isolated_keychain('/unused', []):
                    self.fail('不应进入')
            call.assert_not_called()

    def test_other_platform_does_not_touch_keychain(self):
        with patch('keychain.sys.platform', 'win32'), patch('keychain.security') as call:
            with isolated_keychain('/unused', []):
                pass
            call.assert_not_called()

    def test_only_explicit_hosts_are_trusted_and_failure_restores(self):
        calls = []
        def security(*args):
            calls.append(args)
            if args == ('default-keychain', '-d', 'user'):
                return '"/original/login.keychain-db"\n'
            if args == ('list-keychains', '-d', 'user'):
                return '"/original/login.keychain-db"\n"/original/other.keychain-db"\n'
            return ''
        with TemporaryDirectory() as directory:
            hosts = [Path(directory) / 'Source Host', Path(directory) / 'Packaged Host']
            for host in hosts:
                host.touch()
            with patch('keychain.sys.platform', 'darwin'), patch.dict(os.environ, {
                'CI': 'true', 'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
            }), patch('keychain.security', side_effect=security):
                with self.assertRaisesRegex(ValueError, 'GUI 失败'):
                    with isolated_keychain(directory, hosts):
                        raise ValueError('GUI 失败')
            add = next(call for call in calls if call[0] == 'add-generic-password')
            self.assertNotIn('-A', add)
            self.assertEqual([add[i + 1] for i, arg in enumerate(add) if arg == '-T'], ['', *[h.resolve() for h in hosts]])
            self.assertEqual(calls[-3], ('default-keychain', '-d', 'user', '-s', '/original/login.keychain-db'))
            self.assertEqual(calls[-2], ('list-keychains', '-d', 'user', '-s', '/original/login.keychain-db', '/original/other.keychain-db'))
            self.assertEqual(calls[-1][0], 'delete-keychain')


if __name__ == '__main__':
    unittest.main()
