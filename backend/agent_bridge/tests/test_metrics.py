from datetime import timedelta
import io
import json
import uuid
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from agent_bridge import services
from agent_bridge.models import AssistanceRequest


class AgentMetricsTests(TestCase):
    def test_queue_and_completion_use_stable_timestamps(self):
        user = User.objects.create_user('metrics')
        device, _ = services.create_device(user, name='测试设备', capabilities=['design_polish'])
        item = services.create_request(user, device_id=device.pk, kind='design_polish', idempotency_key=uuid.uuid4(), draft={'title': '标题', 'content': '', 'kind': 'Asset'})
        AssistanceRequest.objects.filter(pk=item.pk).update(created_at=timezone.now() - timedelta(seconds=10))
        item = services.claim(device.pk)
        self.assertIsNotNone(item.claimed_at)
        result = {'title': '标题', 'content': '', 'summary': '', 'questions': []}
        services.finish(device.pk, item.pk, item.attempt_id, result=result)
        out = io.StringIO()
        call_command('agent_metrics', stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(report['statuses'], {'succeeded': 1})
        self.assertGreaterEqual(report['queue_wait']['p50_ms'], 10000)
        self.assertEqual(report['execution_and_delivery']['samples'], 1)
        self.assertNotIn('标题', out.getvalue())

    def test_runner_status_is_readonly_and_device_attempt_isolation(self):
        from rest_framework.test import APIClient
        user = User.objects.create_user('device-owner')
        device, token = services.create_device(user, name='原设备', capabilities=['design_polish'])
        other, other_token = services.create_device(user, name='同账号另一设备', capabilities=['design_polish'])
        item = services.create_request(user, device_id=device.pk, kind='design_polish', idempotency_key=uuid.uuid4(), draft={'title': '标题', 'content': '', 'kind': 'Asset'})
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        status = client.post('/api/agent-runner/status/').json()
        self.assertEqual(status['schema_versions'], [1])
        self.assertEqual(status['device_id'], str(device.pk))
        self.assertEqual(status['owner_id'], str(user.pk))
        self.assertNotIn(token, json.dumps(status))
        browser = APIClient()
        browser.force_login(user)
        self.assertEqual(browser.post('/api/agent-runner/status/').status_code, 401)
        item.refresh_from_db()
        self.assertEqual(item.status, 'queued')
        item = services.claim(device.pk)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        response = client.post(f'/api/agent-runner/requests/{item.pk}/heartbeat/', {'attempt_id': str(item.attempt_id)}, format='json')
        self.assertEqual(response.status_code, 404)
