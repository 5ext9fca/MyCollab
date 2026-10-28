"""独立进程验证锁与退出释放；Windows 原生验证在对应平台执行。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from local_runner.private_files import exclusive_lock, private_directory
from local_runner.state import StateStore
from local_runner.parent_process import ParentProcess


class PrivateFilesTests(unittest.TestCase):
    def test_competing_process_is_rejected_and_crash_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = private_directory(Path(directory) / '中文 状态') / 'runner.lock'
            code = ('import sys,time; from local_runner.private_files import exclusive_lock; '
                    'ctx=exclusive_lock(sys.argv[1]); ctx.__enter__(); print("ready",flush=True); time.sleep(60)')
            child = subprocess.Popen([sys.executable, '-c', code, str(lock)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                with self.assertRaises(ValueError):
                    with exclusive_lock(lock):
                        pass
            finally:
                child.kill()
                child.communicate(timeout=5)
            with exclusive_lock(lock):
                pass

    def test_parent_probe_observes_exit_without_terminating_live_process(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        parent = ParentProcess(child.pid)
        try:
            self.assertTrue(parent.alive())
            self.assertIsNone(child.poll())
            child.terminate()
            child.wait(timeout=5)
            self.assertFalse(parent.alive())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            parent.close()

    @unittest.skipUnless(os.name == 'posix', '符号链接测试需 POSIX')
    def test_linked_state_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.mkdir()
            link = Path(directory) / 'linked'
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                private_directory(link)

    @unittest.skipUnless(os.name == 'nt', '需要 Windows 原生 ACL')
    def test_windows_dacl_is_protected_and_only_current_user_has_access(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / 'config.json', 'https://example.com', 'secret')
            store.status('idle')
            # 固定脚本，路径通过环境传入，不拼接 PowerShell 源码。
            script = ('$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; '
                      '$a=Get-Acl -LiteralPath $env:MYCOLLAB_ACL_TEST_PATH; '
                      '$rules=@($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])); '
                      '@{protected=$a.AreAccessRulesProtected;count=$rules.Count;'
                      'own=($rules[0].IdentityReference.Value -eq $sid)} | ConvertTo-Json -Compress')
            env = {**os.environ, 'MYCOLLAB_ACL_TEST_PATH': str(store.root)}
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=env,
                                    capture_output=True, text=True, check=True, timeout=15)
            self.assertEqual(json.loads(result.stdout), {'protected': True, 'count': 1, 'own': True})
