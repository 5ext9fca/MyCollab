"""显式启用的 Electron GUI 验收，使用独立 PostgreSQL 测试数据库。"""
import os
from pathlib import Path
import subprocess
import shutil
import signal
import runpy
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
        User.objects.create_user('desktop_admin', password='desktop-test-password', is_staff=True)
        frontend = Path(__file__).resolve().parents[2] / 'frontend'
        with TemporaryDirectory(prefix='mycollab-desktop-media-') as media, self.settings(MEDIA_ROOT=media):
            fixture = Path(media) / '模型 验收'
            fixture.mkdir()
            make_fixture = runpy.run_path(str(frontend.parent / 'local_runner/tests/fixture_cli.py'))['model_fixture']
            cli, model = make_fixture(fixture, 'complete')
            process = subprocess.Popen(
                [shutil.which('node') or 'node', str(frontend / 'node_modules/@playwright/test/cli.js'),
                 'test', '--config=playwright.desktop.config.ts', '--global-timeout=150000', '--max-failures=1'],
                cwd=frontend, env={**os.environ, 'MYCOLLAB_TEST_API_TARGET': self.live_server_url,
                              'MYCOLLAB_GUI_OPENCODE': cli, 'MYCOLLAB_GUI_MODEL': model,
                              'MYCOLLAB_GUI_MODEL_COUNTER': str(fixture / 'model-count')},
                start_new_session=os.name != 'nt',
            )
            try:
                self.assertEqual(process.wait(timeout=180), 0,
                                 'Electron GUI 验收失败，见 frontend/test-results/desktop。')
            finally:
                # POSIX 只清理本次独立进程组；Windows 超时则终止指定测试进程树。
                if os.name != 'nt':
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   check=False, capture_output=True, timeout=15)
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=15)
