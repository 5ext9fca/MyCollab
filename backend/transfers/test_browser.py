"""显式启用的真实浏览器验收，使用独立 PostgreSQL 测试库。"""
import os
from pathlib import Path
import subprocess
import signal
from unittest import skipUnless

from django.test import LiveServerTestCase, override_settings

from accounts.models import User


@skipUnless(os.environ.get("MYCOLLAB_BROWSER_TEST") == "1", "设置 MYCOLLAB_BROWSER_TEST=1 启用真实浏览器验收")
@override_settings(CSRF_TRUSTED_ORIGINS=["http://localhost:5179"], ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"])
class FileTransferBrowserTests(LiveServerTestCase):
    def test_browser_transfer(self):
        for username in ["transfer_sender", "transfer_receiver"]:
            User.objects.create_user(username, password="browser-test-password")
        frontend = Path(__file__).resolve().parents[2] / "frontend"
        process = subprocess.Popen(
            ["npm", "run", "test:transfer"], cwd=frontend,
            env={**os.environ, "MYCOLLAB_TEST_API_TARGET": self.live_server_url},
            start_new_session=True,
        )
        try:
            self.assertEqual(process.wait(timeout=480), 0, "浏览器验收失败，见 Playwright 输出与 frontend/test-results。")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
