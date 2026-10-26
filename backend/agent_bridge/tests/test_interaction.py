import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from agent_bridge import services as bridge
from agent_bridge.models import InteractionSession, InteractionPermission, InteractionCommand
from agent_bridge.interaction_protocol import digest
from missions import services
from missions.tests import utils


class InteractionTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user('interaction-owner')
        self.other = User.objects.create_user('interaction-other')
        self.device, token = bridge.create_device(self.actor, name='本机', capabilities=['code_implement'])
        mission = utils.claim(self.actor, services.create_mission(actor=self.actor, title='代码交互'))
        self.execution = services.create_code_execution(actor=self.actor, mission_id=mission.pk, device_id=self.device.pk,
            repository_key_value='demo', expected_version=mission.version, instructions='实现', idempotency_key=uuid.uuid4())
        self.item = bridge.claim(self.device.pk)
        self.browser = APIClient(); self.browser.force_login(self.actor)
        self.runner = APIClient(); self.runner.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        self.url = f'/api/assistance-requests/{self.item.pk}/interaction/'
        self.runner_url = f'/api/agent-runner/requests/{self.item.pk}/interaction/'
        self.binding = {'attempt_id': str(self.item.attempt_id), 'session_nonce': str(uuid.uuid4())}
        self.assertEqual(self.runner.post(self.runner_url + 'open/', {**self.binding, 'supports_followup': True, 'supports_permissions': True}, format='json').status_code, 200)

    def exchange(self, **kwargs):
        return self.runner.post(self.runner_url + 'exchange/', {**self.binding, **kwargs}, format='json')

    def command(self, kind='followup', payload=None, **kwargs):
        data = {**self.binding, 'command_id': str(uuid.uuid4()), 'kind': kind, 'payload': payload or {'text': '请覆盖负数'}}
        data.update(kwargs)
        return self.browser.post(self.url, data, format='json')

    def permission(self):
        operation = {'action': 'edit', 'paths': ['rules.py']}
        event = {'event_id': str(uuid.uuid4()), 'kind': 'permission_requested', 'payload': {'permission_id': str(uuid.uuid4()), 'operation': operation}}
        self.assertEqual(self.exchange(events=[event]).status_code, 200)
        return event, {'permission_id': event['payload']['permission_id'], 'operation_digest': digest(operation), 'decision': 'approve'}

    def test_owner_only_and_authentication_separation(self):
        self.browser.force_login(self.other)
        self.assertEqual(self.browser.get(self.url).status_code, 404)
        self.assertEqual(self.command().status_code, 404)
        self.assertIn(self.runner.get(self.url).status_code, (401, 403))
        self.assertIn(self.browser.post(self.runner_url + 'exchange/', self.binding, format='json').status_code, (401, 403))

    def test_command_retry_and_ack_are_idempotent(self):
        key = str(uuid.uuid4())
        self.assertEqual(self.command(command_id=key).status_code, 201)
        self.assertEqual(self.command(command_id=key).status_code, 201)
        self.assertEqual(self.command(command_id=key, payload={'text': '不同内容'}).status_code, 409)
        self.assertEqual(InteractionCommand.objects.count(), 1)
        self.assertEqual(len(self.exchange().data['commands']), 1)
        ack = [{'command_id': key, 'status': 'applied'}]
        self.assertEqual(self.exchange(acknowledgements=ack).data['commands'], [])
        self.assertEqual(self.exchange(acknowledgements=ack).status_code, 200)
        self.assertEqual(self.browser.get(self.url).data['commands'][0]['status'], 'applied')

    def test_events_cursor_dedup_and_content_conflict(self):
        event = {'event_id': str(uuid.uuid4()), 'kind': 'assistant_message', 'payload': {'text': '正在检查'}}
        self.assertEqual(self.exchange(events=[event]).data['sequences'], [1])
        self.assertEqual(self.exchange(events=[event]).data['sequences'], [1])
        self.assertEqual(self.exchange(events=[{**event, 'payload': {'text': '变更'}}]).status_code, 409)
        self.assertEqual(self.browser.get(self.url + '?after=1').data['events'], [])
        self.assertEqual(self.browser.get(self.url).data['next_cursor'], 1)

    def test_permission_is_single_use_and_binds_exact_operation(self):
        event, payload = self.permission()
        self.assertEqual(self.command('permission_reply', {**payload, 'operation_digest': '0' * 64}).status_code, 409)
        self.assertEqual(self.command('permission_reply', payload).status_code, 201)
        self.assertEqual(self.command('permission_reply', payload).status_code, 409)
        closed = {'event_id': str(uuid.uuid4()), 'kind': 'permission_closed', 'payload': {'permission_id': payload['permission_id'], 'outcome': 'approved'}}
        self.assertEqual(self.exchange(events=[closed]).status_code, 200)
        self.assertEqual(InteractionPermission.objects.get().status, 'approved')

    def test_expiry_cancel_and_wrong_session_refuse_commands(self):
        _, payload = self.permission()
        InteractionPermission.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.command('permission_reply', payload).status_code, 409)
        self.assertEqual(self.command(session_nonce=str(uuid.uuid4())).status_code, 409)
        self.assertEqual(self.command(attempt_id=str(uuid.uuid4())).status_code, 409)
        bridge.cancel(self.actor, self.item.pk)
        self.assertFalse(self.browser.get(self.url).data['active'])
        self.assertEqual(self.command().status_code, 409)
        self.assertEqual(self.exchange().status_code, 409)

    def test_late_lease_and_revoked_device(self):
        self.item.lease_expires_at = timezone.now() - timedelta(seconds=1)
        self.item.save(update_fields=['lease_expires_at'])
        self.assertEqual(self.command().status_code, 409)
        self.assertEqual(self.exchange().status_code, 409)
        bridge.revoke_device(self.actor, self.device.pk)
        self.assertEqual(self.browser.get(self.url).status_code, 403)

    def test_bounded_events_and_unknown_fields(self):
        self.assertEqual(self.exchange(events=[{'event_id': str(uuid.uuid4()), 'kind': 'raw_log', 'payload': {}}]).status_code, 400)
        self.assertEqual(self.command(payload={'text': 'a' * 4001}).status_code, 400)
        self.assertEqual(self.command(payload={'text': '说明', 'shell': 'pwd'}).status_code, 400)
        InteractionSession.objects.update(event_count=1000)
        self.assertEqual(self.exchange(events=[{'event_id': str(uuid.uuid4()), 'kind': 'assistant_message', 'payload': {'text': '超过限额'}}]).status_code, 409)

    def test_closed_session_does_not_resume(self):
        self.assertEqual(self.exchange(close=True).status_code, 200)
        self.assertEqual(self.command().status_code, 409)
        self.assertFalse(self.browser.get(self.url).data['active'])
        self.assertEqual(self.runner.post(self.runner_url + 'open/', {**self.binding, 'supports_followup': True, 'supports_permissions': True}, format='json').status_code, 409)

    def test_close_drains_queued_commands_before_closing(self):
        response = self.command()
        key = response.data['command_id']
        first = self.exchange(close=True)
        self.assertFalse(first.data['closed'])
        self.assertEqual(len(first.data['commands']), 1)
        second = self.exchange(close=True, acknowledgements=[{'command_id': str(key), 'status': 'applied'}])
        self.assertTrue(second.data['closed'])

    def test_local_runner_bridge_permission_and_followup_roundtrip(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest.mock import Mock
        import sys
        import_root = str(Path(__file__).resolve().parents[3])
        sys.path.insert(0, import_root)
        self.addCleanup(lambda: sys.path.remove(import_root) if import_root in sys.path else None)
        from local_runner.interaction import Interaction
        from rest_framework.renderers import JSONRenderer
        browser = self.browser
        runner = self.runner
        binding = self.binding
        # 使用另一会话前撤销测试初始化的空会话，保持真实领取记录。
        InteractionSession.objects.all().delete()
        class Client:
            def post(inner, path, payload):
                response = runner.post('/api/agent-runner/' + path, payload, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                return json.loads(JSONRenderer().render(response.data))
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / 'workspace'; workspace.mkdir()
            native = Mock()
            item = {'id': 'per_native', 'sessionID': 'ses_native', 'action': 'edit', 'resources': ['rules.py']}
            native.call.return_value = {'data': [item]}
            interaction = Interaction(Client(), {'id': str(self.item.pk), 'attempt_id': str(self.item.attempt_id)}, native, 'ses_native', workspace, ['rules.py'], Path(root))
            self.binding = interaction.binding
            interaction.poll_permissions(); interaction.exchange()
            state = browser.get(self.url).data
            permission = state['permissions'][0]
            self.assertEqual(self.command('permission_reply', {'permission_id': str(permission['permission_id']), 'operation_digest': permission['operation_digest'], 'decision': 'approve'}).status_code, 201)
            interaction.exchange(); interaction.exchange()
            self.assertEqual(InteractionPermission.objects.get().status, 'approved')
            self.assertEqual(InteractionCommand.objects.get().status, 'applied')
            self.assertEqual(self.command().status_code, 201)
            interaction.exchange(); interaction.exchange()
            self.assertEqual(InteractionCommand.objects.filter(status='applied').count(), 2)
            self.assertTrue(interaction.exchange(close=True))
            self.assertFalse(browser.get(self.url).data['active'])
            self.assertEqual([c.args[2] for c in native.call.call_args_list if c.args[0] == 'POST' and c.args[1].endswith('/reply')], [{'decision': 'once'}])
        self.binding = binding

    def test_cleanup_removes_private_history_without_removing_execution(self):
        from django.core.management import call_command
        InteractionSession.objects.update(created_at=timezone.now() - timedelta(days=8))
        call_command('cleanup_assistance')
        self.assertTrue(InteractionSession.objects.exists())
        bridge.cancel(self.actor, self.item.pk)
        call_command('cleanup_assistance')
        self.assertFalse(InteractionSession.objects.exists())
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.request_id, self.item.pk)


from django.test import TransactionTestCase
from missions.tests.test_concurrency_features import run_concurrently


class InteractionConcurrencyTests(TransactionTestCase):
    setUp = InteractionTests.setUp
    exchange = InteractionTests.exchange
    permission = InteractionTests.permission

    def test_two_decisions_only_create_one_command(self):
        _, payload = self.permission()
        def decide():
            services.create_interaction_command(self.actor, self.item.pk,
                self.item.attempt_id, uuid.UUID(self.binding['session_nonce']), uuid.uuid4(), 'permission_reply', payload)
        results = run_concurrently(decide, decide)
        self.assertEqual(list(results.values()).count('ok'), 1, results)
        self.assertEqual(InteractionCommand.objects.count(), 1)
