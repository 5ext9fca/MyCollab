"""真实 HTTP + 确定性本地图像适配器，普通回归不访问模型。"""
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
from agent_bridge.tests.test_images import png
from agent_bridge.image_protocol import inspect_png
from library.models import LibraryFile
from missions import services
from missions.tests import utils


@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class ImageRoundTripTests(LiveServerTestCase):
    def test_generate_edit_select_upload_submit_and_review(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from local_runner.__main__ import BridgeClient
        from local_runner.images import execute_image, select
        original = socket.socket.connect
        def local_only(connection, address):
            if isinstance(address, tuple) and address[0] not in ('localhost', '127.0.0.1', '::1'):
                raise OSError('测试服务器不得访问外网。')
            return original(connection, address)
        actor = User.objects.create_user('image-roundtrip')
        device, token = bridge.create_device(actor, name='本地假适配器', capabilities=['image_generate', 'image_edit'])
        asset = services.create_design_element(actor=actor, title='叶片', kind='Asset')
        mission = utils.claim(actor, services.create_mission(actor=actor, title='图像任务', asset_ids=[asset.pk]))
        browser = APIClient()
        browser.force_login(actor)
        runner = BridgeClient(self.live_server_url, token)
        def adapter(request, directory, references, **kwargs):
            self.assertEqual(len(references), 1 if request['kind'] == 'image_edit' else 0)
            values = []
            for index in range(2):
                name = f'candidate_{index + 1}.png'
                (directory / name).write_bytes(png(index))
                values.append(dict(key=f'candidate_{index + 1}', name=name, **inspect_png(png(index))))
            return {'candidates': values}
        def normalize(source, destination):
            destination.write_bytes(source.read_bytes())
            return inspect_png(destination.read_bytes())
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory + '/media'), patch.object(socket.socket, 'connect', local_only), patch('local_runner.images.run', side_effect=adapter) as model, patch('local_runner.images.normalize', side_effect=normalize):
            config = {'image_adapter': 'codex', 'image_output_dir': directory + '/outputs'}
            previous, reference_ids = None, []
            for kind in ('image_generate', 'image_edit'):
                response = browser.post('/api/mission-executions/', {'mission_id': str(mission.pk), 'asset_id': str(asset.pk), 'device_id': str(device.pk), 'kind': kind, 'expected_version': mission.version, 'asset_version': asset.version, 'instructions': '生成/编辑叶片', 'reference_ids': reference_ids, 'idempotency_key': str(uuid.uuid4()), 'previous_id': previous}, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                previous = response.data['id']
                claimed = runner.post('claim/', {})
                count = LibraryFile.objects.count()
                execute_image(runner, claimed, config)
                self.assertEqual(LibraryFile.objects.count(), count)
                select(runner, config, claimed['id'], ['candidate_2'])
                self.assertEqual(LibraryFile.objects.count(), count + 1)
                result = browser.get(f'/api/mission-executions/{previous}/').json()
                self.assertEqual(result['status'], 'succeeded')
                uploaded = [c for c in result['candidates'] if c['file_id']]
                self.assertEqual(len(uploaded), 1)
                reference_ids = [uploaded[0]['file_id']]
                mission.refresh_from_db()
                self.assertEqual(mission.status, 'InProgress')
            self.assertEqual(model.call_count, 2)
            mission = utils.submit(actor, mission, execution_candidate_ids=[uploaded[0]['id']])
            self.assertEqual(mission.current_submission.execution_artifacts.count(), 1)
            mission = utils.review(actor, mission)
            self.assertEqual(mission.status, 'Done')
