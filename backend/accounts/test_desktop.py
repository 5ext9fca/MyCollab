"""显式启用的 Electron GUI 验收，使用独立 PostgreSQL 测试数据库。"""
import os
from pathlib import Path
import subprocess
import shutil
from unittest import skipUnless
from tempfile import TemporaryDirectory

from django.test import LiveServerTestCase, override_settings
from accounts.models import User


@skipUnless(os.environ.get('MYCOLLAB_DESKTOP_TEST') == '1', '设置 MYCOLLAB_DESKTOP_TEST=1 启用 Electron GUI 验收')
@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class DesktopGuiTests(LiveServerTestCase):
    def test_desktop(self):
        User.objects.create_user('desktop_user', password='desktop-test-password')
        User.objects.create_user('desktop_other', password='desktop-test-password')
        frontend = Path(__file__).resolve().parents[2] / 'frontend'
        with TemporaryDirectory(prefix='mycollab-desktop-media-') as media, self.settings(MEDIA_ROOT=media):
            result = subprocess.run(
                [shutil.which('npm') or 'npm', 'exec', '--', 'playwright', 'test', '--config=playwright.desktop.config.ts'],
                cwd=frontend, env={**os.environ, 'MYCOLLAB_TEST_API_TARGET': self.live_server_url},
                timeout=180, check=False,
            )
        self.assertEqual(result.returncode, 0, 'Electron GUI 验收失败，见 frontend/test-results/desktop。')
