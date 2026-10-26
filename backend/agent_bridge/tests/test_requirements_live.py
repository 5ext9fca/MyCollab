"""仅显式启用时，用真实本地 OpenCode 验证需求文档导出。"""
import os
from pathlib import Path
import socket
import sys
import unittest
import uuid
from unittest.mock import patch
from django.test import LiveServerTestCase, override_settings
from rest_framework.test import APIClient
from accounts.models import User
from agent_bridge import services
from missions import services as business


@unittest.skipUnless(os.environ.get('MYCOLLAB_LIVE_MODEL'), '仅在显式指定本机模型时运行真实接入')
@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class RequirementsAcceptanceTests(LiveServerTestCase):
    def test_real_markdown_export(self):
        original_connect = socket.socket.connect
        def local_only(connection, address):
            if isinstance(address, tuple) and address[0] not in ('localhost', '127.0.0.1', '::1'):
                raise OSError('服务器只允许本机通信，供应商调用须由本地子进程完成。')
            return original_connect(connection, address)
        with patch.object(socket.socket, 'connect', local_only):
            import_root = str(Path(__file__).resolve().parents[3])
            sys.path.insert(0, import_root)
            self.addCleanup(lambda: sys.path.remove(import_root))
            from local_runner.__main__ import BridgeClient, execute
            actor = User.objects.create_user('requirements-live')
            mission = business.create_mission(actor=actor, title='角色说明', content='绿色披风，不增加武器。尺寸与文件格式尚未确定。', acceptance_criteria='明确绿色披风且没有武器。')
            device, token = services.create_device(actor, name='真实文档测试', capabilities=['agent_requirements'])
            browser = APIClient(); browser.force_login(actor)
            response = browser.post('/api/assistance-requests/', {'device_id': str(device.pk), 'kind': 'agent_requirements', 'idempotency_key': str(uuid.uuid4()), 'draft': {}, 'object_id': str(mission.pk), 'base_version': mission.version}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            runner = BridgeClient(self.live_server_url, token)
            claimed = runner.post('claim/', {})
            execute(runner, claimed, os.environ['MYCOLLAB_LIVE_MODEL'], 'opencode')
            detail = browser.get(f"/api/assistance-requests/{claimed['id']}/").json()
            self.assertEqual(detail['status'], 'succeeded', detail.get('error'))
            markdown = detail['result']['markdown']
            self.assertIn('## 待澄清事项', markdown)
            self.assertIn('绿色', markdown)
            self.assertIn(str(mission.pk), markdown)
            mission.refresh_from_db()
            self.assertEqual(mission.status, 'Open')
            self.assertEqual(mission.version, 1)
            print('真实 OpenCode 导出通过：返回完整 Markdown，保留来源标识，Mission 未改变。')
