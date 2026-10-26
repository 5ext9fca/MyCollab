"""真实 HTTP 的隔离代码交付闭环，模型为确定性假适配器。"""
from pathlib import Path
import socket
import sys
import tempfile
import uuid
from unittest.mock import patch

from django.test import LiveServerTestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from agent_bridge import services as bridge
from library.models import LibraryFile
from missions import services
from missions.tests import utils


@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class CodeRoundTripTests(LiveServerTestCase):
    def test_local_implementation_then_explicit_publish_and_human_review(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from local_runner.__main__ import BridgeClient
        from local_runner.code_execution import execute_code, publish
        from local_runner.code_workspace import git
        original = socket.socket.connect
        def local_only(connection, address):
            if isinstance(address, tuple) and address[0] not in ('localhost', '127.0.0.1', '::1'):
                raise OSError('测试服务器不得访问外网。')
            return original(connection, address)
        actor = User.objects.create_user('code-roundtrip')
        device, token = bridge.create_device(actor, name='代码本机', capabilities=['code_implement'])
        mission = utils.claim(actor, services.create_mission(actor=actor, title='规则实现'))
        browser = APIClient(); browser.force_login(actor)
        runner = BridgeClient(self.live_server_url, token)
        def model(request, directory, paths, **kwargs):
            (directory / 'rules.py').write_text('VALUE = 2\n')
            return '实现规则，验证由 Runner 执行。'
        with tempfile.TemporaryDirectory() as temporary, override_settings(MEDIA_ROOT=temporary + '/media'), patch.object(socket.socket, 'connect', local_only), patch('local_runner.code_execution.opencode_code.run', side_effect=model) as adapter:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'rules.py').write_text('VALUE = 1\n')
            git(source, 'init', '-q'); git(source, 'add', '--all')
            git(source, '-c', 'user.name=Test', '-c', 'user.email=test@invalid', 'commit', '-qm', '基线')
            config = {'code_output_dir': str(root / 'outputs'), 'model': 'fake/model', 'repositories': {'demo': {
                'path': str(source), 'writable_paths': ['rules.py'], 'verification': [{'id': 'unit', 'label': '规则测试',
                    'argv': [sys.executable, '-c', 'from rules import VALUE; assert VALUE == 2']}]}}}
            response = browser.post('/api/code-executions/', {'mission_id': str(mission.pk), 'device_id': str(device.pk), 'repository_key': 'demo', 'expected_version': mission.version, 'instructions': '实现规则', 'idempotency_key': str(uuid.uuid4())}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            execution_id = response.data['id']
            claimed = runner.post('claim/', {})
            execute_code(runner, claimed, config)
            self.assertFalse(LibraryFile.objects.exists())
            publish(runner, config, claimed['id'])
            publish(runner, config, claimed['id'])
            self.assertEqual(LibraryFile.objects.count(), 1)
            self.assertEqual(adapter.call_count, 1)
            result = browser.get(f'/api/code-executions/{execution_id}/').json()
            self.assertEqual(result['status'], 'succeeded')
            self.assertEqual(result['report']['verification'][0]['status'], 'passed')
            self.assertEqual((source / 'rules.py').read_text(), 'VALUE = 1\n')
            mission.refresh_from_db(); self.assertEqual(mission.status, 'InProgress')
            response = browser.post(f'/api/missions/{mission.pk}/submit/', {'expected_version': mission.version,
                'description': '实现完成', 'verification_description': '人工检查补丁和规则测试', 'code_execution_ids': [execution_id]}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            mission.refresh_from_db()
            self.assertEqual(mission.current_submission.code_artifacts.count(), 1)
            self.assertEqual(utils.review(actor, mission).status, 'Done')
