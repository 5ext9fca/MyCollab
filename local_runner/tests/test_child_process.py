"""Windows Job 原生验收必须在 Windows 运行；通用测试验证创建失败不降级。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from local_runner import windows_job
from local_runner.child_process import spawn
from local_runner.parent_process import ParentProcess


class ProcessCreationTests(unittest.TestCase):
    def test_windows_assignment_failure_kills_suspended_process_without_fallback(self):
        process = Mock(pid=123)
        process.poll.return_value = None
        with patch('local_runner.child_process.os.name', 'nt'), \
             patch('local_runner.windows_job.protect_runner_tree'), \
             patch('local_runner.windows_job.ProcessJob') as job, \
             patch('local_runner.child_process.subprocess.Popen', return_value=process) as popen:
            job.return_value.assign_and_resume.side_effect = OSError('job unavailable')
            with self.assertRaises(OSError):
                spawn(['opencode', 'run'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self.assertEqual(popen.call_count, 1)
            self.assertTrue(popen.call_args.kwargs['creationflags'] & 4)
            process.kill.assert_called_once()
            process.wait.assert_called_once()
            job.return_value.close.assert_called_once()

    def test_job_cleanup_runs_even_when_direct_child_has_already_exited(self):
        from local_runner.opencode import terminate
        process = Mock()
        process.poll.return_value = 0
        with patch('local_runner.opencode.os.name', 'nt'):
            terminate(process)
        process._mycollab_job.close.assert_called_once()
        process.wait.assert_called_once()


@unittest.skipUnless(os.name == 'nt', '需要 Windows 原生 Job Object')
class WindowsJobTests(unittest.TestCase):
    def test_runner_crash_terminates_model_and_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'tree.json'
            child_code = ('import subprocess,sys,os,time,json; from pathlib import Path; '
                          'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                          'Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid])); time.sleep(60)')
            runner_code = ('import sys,time; from local_runner.child_process import spawn; '
                           'spawn([sys.executable,"-c",sys.argv[1],sys.argv[2]]); time.sleep(60)')
            runner = subprocess.Popen([sys.executable, '-c', runner_code, child_code, str(marker)])
            monitors = []
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), '模型树未启动')
                monitors = [ParentProcess(pid) for pid in json.loads(marker.read_text())]
                self.assertTrue(all(item.alive() for item in monitors))
                runner.kill()
                runner.wait(timeout=5)
                deadline = time.monotonic() + 5
                while any(item.alive() for item in monitors) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(all(not item.alive() for item in monitors))
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.wait(timeout=5)
                for item in monitors:
                    if item.alive():
                        subprocess.run(['taskkill.exe', '/PID', str(item.pid), '/T', '/F'], capture_output=True, timeout=5)
                    item.close()
