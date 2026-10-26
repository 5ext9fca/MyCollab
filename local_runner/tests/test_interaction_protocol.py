"""共享交互协议拒绝任意事件、外部路径与长期授权。"""
import unittest
from uuid import uuid4
from backend.agent_bridge.interaction_protocol import validate_event, validate_operation, digest
from backend.agent_bridge.protocol import ProtocolError


class InteractionProtocolTests(unittest.TestCase):
    def test_only_bounded_public_messages(self):
        event = {'event_id': str(uuid4()), 'kind': 'assistant_message', 'payload': {'text': '请确认边界条件。'}}
        self.assertEqual(validate_event(event), event)
        for payload in ({'text': 'a' * 4001}, {'text': '说明', 'raw_event': {}}, {'text': ''}):
            with self.assertRaises(ProtocolError):
                validate_event({**event, 'payload': payload})
        with self.assertRaises(ProtocolError):
            validate_event({**event, 'kind': 'tool_log'})

    def test_permission_cannot_expand_local_boundary(self):
        self.assertEqual(validate_operation({'action': 'edit', 'paths': ['src/rules.py']})['action'], 'edit')
        for operation in [
            {'action': 'shell', 'paths': ['src/rules.py']},
            *[{'action': 'edit', 'paths': [p]} for p in ['/tmp/a', '../a', '.git/config', '.env', 'opencode.json', 'src/.env.local']],
            {'action': 'edit', 'paths': ['a', 'a']},
            {'action': 'edit', 'paths': ['a'], 'remember': True},
        ]:
            with self.assertRaises(ProtocolError):
                validate_operation(operation)

    def test_digest_binds_exact_operation(self):
        self.assertEqual(digest({'paths': ['a'], 'action': 'edit'}), digest({'action': 'edit', 'paths': ['a']}))
        self.assertNotEqual(digest({'action': 'edit', 'paths': ['a']}), digest({'action': 'edit', 'paths': ['b']}))

    def test_identifiers_and_outcomes_are_strict(self):
        event = {'event_id': str(uuid4()), 'kind': 'permission_closed', 'payload': {'permission_id': str(uuid4()), 'outcome': 'expired'}}
        validate_event(event)
        with self.assertRaises(ProtocolError):
            validate_event({**event, 'event_id': '/private/session'})
        with self.assertRaises(ProtocolError):
            validate_event({**event, 'payload': {**event['payload'], 'outcome': 'always'}})
