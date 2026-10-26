import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from local_runner.interaction import Interaction
from local_runner.opencode import LocalFailure
from local_runner.opencode_interactive import interactive_configuration


class InteractionRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name); self.workspace = self.directory / 'workspace'; self.workspace.mkdir()
        self.native = Mock(); self.native.call.return_value = {'data': []}
        self.client = Mock(); self.client.post.return_value = {'commands': [], 'closed': False}
        self.request = {'id': str(uuid4()), 'attempt_id': str(uuid4())}
        self.interaction = Interaction(self.client, self.request, self.native, 'ses_test', self.workspace, ['rules.py'], self.directory)

    def command(self, kind='followup', payload=None):
        return {'command_id': str(uuid4()), 'kind': kind, 'payload': payload or {'text': '考虑负数'},
            'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}

    def permission(self, **changes):
        value = {'id': 'per_test', 'sessionID': 'ses_test', 'action': 'edit', 'resources': ['rules.py'], 'metadata': {'diff': 'private'}}
        value.update(changes)
        self.native.call.return_value = {'data': [value]}
        self.interaction.poll_permissions()
        return value

    def test_followup_dedup_survives_ack_retry(self):
        command = self.command()
        self.interaction.apply(command); self.interaction.apply(command)
        self.assertEqual(self.native.call.call_count, 1)
        self.assertEqual(self.native.call.call_args.args[2]['delivery'], 'steer')
        state = json.loads(self.interaction.path.read_text())
        self.assertEqual(state['commands'][command['command_id']]['status'], 'applied')
        self.assertEqual(self.interaction.path.stat().st_mode & 0o077, 0)

    def test_unknown_delivery_result_never_repeats_native_call(self):
        command = self.command()
        self.native.call.side_effect = OSError('断线')
        with self.assertRaises(OSError): self.interaction.apply(command)
        with self.assertRaises(LocalFailure): self.interaction.apply(command)
        self.assertEqual(self.native.call.call_count, 1)

    def test_permission_only_once_and_exact_native_operation(self):
        item = self.permission()
        key, saved = next(iter(self.interaction.permissions.items()))
        command = self.command('permission_reply', {'permission_id': key, 'operation_digest': saved['operation_digest'], 'decision': 'approve'})
        self.interaction.apply(command); self.interaction.apply(command)
        posts = [call for call in self.native.call.call_args_list if call.args[0] == 'POST']
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].args[2], {'decision': 'once'})
        self.assertEqual(saved['status'], 'approved')
        self.assertNotIn('private', json.dumps(self.interaction.events))

    def test_changed_permission_and_expired_command_rejected(self):
        item = self.permission()
        key, saved = next(iter(self.interaction.permissions.items()))
        self.native.call.return_value = {'data': [{**item, 'metadata': {'diff': 'changed'}}]}
        self.interaction.apply(self.command('permission_reply', {'permission_id': key, 'operation_digest': saved['operation_digest'], 'decision': 'approve'}))
        self.assertFalse(any(call.args[0] == 'POST' for call in self.native.call.call_args_list))
        command = self.command(); command['expires_at'] = '2000-01-01T00:00:00+00:00'
        self.interaction.apply(command)
        self.assertEqual(self.interaction.commands[command['command_id']]['status'], 'rejected')

    def test_timeout_rejects_and_disallowed_tool_never_offered(self):
        self.permission()
        saved = next(iter(self.interaction.permissions.values())); saved['deadline'] = 0
        self.interaction.poll_permissions()
        self.assertEqual(self.native.call.call_args.args[2], {'decision': 'reject'})
        self.assertEqual(saved['status'], 'expired')
        before = len(self.interaction.permissions)
        self.permission(id='per_shell', action='shell', resources=['echo hello'])
        self.assertEqual(len(self.interaction.permissions), before)
        self.assertEqual(self.native.call.call_args.args[2], {'decision': 'reject'})

    def test_paths_and_symlinks_do_not_expand_permission(self):
        for resource in ['../outside', '/etc/passwd', '.env', 'other.py']:
            with self.subTest(resource=resource):
                with self.assertRaises(ValueError):
                    self.interaction.operation({'sessionID': 'ses_test', 'action': 'edit', 'resources': [resource]})
        (self.workspace / 'rules.py').symlink_to(self.directory / 'outside')
        with self.assertRaises(ValueError):
            self.interaction.operation({'sessionID': 'ses_test', 'action': 'edit', 'resources': ['rules.py']})

    def test_configuration_only_tightens_existing_permissions(self):
        config = interactive_configuration(['rules.py'])
        edits = [rule for rule in config['permissions'] if rule['action'] == 'edit' and rule['resource'] == 'rules.py']
        self.assertEqual(edits[0]['effect'], 'ask')
        self.assertEqual(config['permissions'][0], {'action': '*', 'resource': '*', 'effect': 'deny'})
        self.assertIn({'action': 'tool.use', 'resource': 'external_directory:*', 'effect': 'deny'}, config['policies'])

    def test_event_limit_stops_details_and_rejects_new_approval(self):
        self.interaction.event_count = 1000
        self.assertFalse(self.interaction.event('assistant_message', {'text': '超限后仅保留本地'}))
        self.permission()
        self.assertEqual(self.native.call.call_args.args[2], {'decision': 'reject'})
        self.assertEqual(self.interaction.events, [])

    def test_heartbeat_failure_interrupts_native_session(self):
        from local_runner.opencode_interactive import run
        from local_runner.opencode import Cancelled
        clock = [0]
        native = Mock()
        def call(method, path, payload=None):
            if path == '/api/session': return {'data': {'id': 'ses_cancel'}}
            if path.endswith('/permission'): return {'data': []}
            if '/message?' in path: return {'data': []}
            if path == '/api/session/active': return {'data': {'ses_cancel': {}}}
            if path == '/api/session/ses_cancel': return {'data': {'time': {}}}
            return None
        native.call.side_effect = call
        self.interaction.path.unlink()
        with patch('local_runner.opencode_interactive.PrivateServer') as server, patch('local_runner.opencode_interactive.time.monotonic', side_effect=lambda: clock[0]), patch('local_runner.opencode_interactive.time.sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            server.return_value.__enter__.return_value = native
            with self.assertRaises(Cancelled):
                run({**self.request, 'kind': 'code_implement', 'schema_version': 1, 'input': {}}, self.workspace, ['rules.py'], model='test/model', client=self.client, heartbeat=lambda: False)
            native.call.assert_any_call('POST', '/api/session/ses_cancel/interrupt')
            server.return_value.__exit__.assert_called_once()
