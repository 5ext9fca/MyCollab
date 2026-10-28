from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from local_runner.__main__ import execute
from local_runner.state import StateStore


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'config.json'
        self.store = StateStore(self.config, 'https://example.com', 'secret')
        self.request = {'id': 'request', 'attempt_id': 'attempt',
                        'lease_expires_at': (datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat()}
        self.payload = {'attempt_id': 'attempt', 'result': {'title': '候选'}}

    @patch('local_runner.__main__.run', return_value={'title': '候选'})
    def test_restart_delivers_saved_result_without_second_model_call(self, run):
        disconnected = Mock()
        disconnected.post.side_effect = OSError()
        execute(disconnected, self.request, 'provider/model', 'opencode', self.store)
        self.assertEqual(self.store.snapshot()['pending_results'], 1)
        recovered = StateStore(self.config, 'https://example.com', 'secret')
        client = Mock()
        client.post.return_value = {"status": "succeeded"}
        self.assertTrue(recovered.recover(client))
        client.post.assert_called_once_with('requests/request/result/', self.payload)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(recovered.snapshot()['pending_results'], 0)

    def test_lost_ack_retries_same_payload_and_terminal_is_not_overwritten(self):
        path = self.store.save_result(self.request, self.payload)
        client = Mock()
        client.post.side_effect = HTTPError('url', 409, 'terminal', {}, None)
        self.assertTrue(self.store.recover(client))
        self.assertEqual(self.store.snapshot()['rejected_results'], 1)
        self.store.recover(client)
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(self.store.read(path)['payload'], self.payload)

    def test_revoked_credentials_preserve_pending_and_stop_recovery(self):
        self.store.save_result(self.request, self.payload)
        client = Mock()
        client.post.side_effect = HTTPError('url', 401, 'unauthorized', {}, None)
        with self.assertRaises(HTTPError):
            self.store.recover(client)
        self.assertEqual(self.store.snapshot()['pending_results'], 1)

    def test_device_and_server_isolation_and_private_permissions(self):
        path = self.store.save_result(self.request, self.payload)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for server, token in [('https://other.com', 'secret'), ('https://example.com', 'other')]:
            self.assertEqual(list(StateStore(self.config, server, token).records()), [])
        self.assertNotIn('secret', path.read_text())

    def test_single_instance_lock_and_crash_journal_does_not_execute(self):
        with self.store.lock():
            with self.assertRaises(ValueError):
                with self.store.lock():
                    pass
        with self.store.lock():
            self.store.begin(self.request)
        client = Mock()
        self.store.recover(client)
        client.post.assert_not_called()

    def test_retention_is_bounded(self):
        self.store.save_result(self.request, self.payload)
        with patch('local_runner.state.time.time', return_value=10**12):
            self.assertEqual(list(self.store.records()), [])

    @patch('local_runner.__main__.run')
    def test_transient_heartbeat_failure_only_within_known_lease(self, run):
        client = Mock()
        client.post.side_effect = OSError()
        def model(*args, heartbeat, **kwargs):
            self.assertTrue(heartbeat())
            with patch('local_runner.__main__.time.monotonic', return_value=10**12):
                self.assertFalse(heartbeat())
            return {'title': '候选'}
        run.side_effect = model
        execute(client, self.request, 'provider/model', 'opencode', self.store)

    @patch('local_runner.__main__.run')
    def test_explicit_cancellation_stops_even_inside_lease(self, run):
        client = Mock()
        client.post.return_value = {'status': 'cancelled'}
        def model(*args, heartbeat, **kwargs):
            self.assertFalse(heartbeat())
            return {'title': '候选'}
        run.side_effect = model
        execute(client, self.request, 'provider/model', 'opencode', self.store)

    def test_invalid_ack_never_discards_result(self):
        self.store.save_result(self.request, self.payload)
        client = Mock()
        client.post.return_value = None
        self.assertFalse(self.store.recover(client))
        self.assertEqual(self.store.snapshot()['pending_results'], 1)

    @patch('local_runner.__main__.run')
    def test_already_expired_lease_does_not_call_model(self, run):
        self.request['lease_expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        execute(Mock(), self.request, 'provider/model', 'opencode', self.store)
        run.assert_not_called()

    def test_status_file_exposes_only_small_delivery_summary(self):
        self.store.save_result(self.request, self.payload)
        self.store.status('delivering')
        summary = self.store.read(self.store.root / 'status.json')
        self.assertEqual(summary['pending_results'], 1)
        self.assertNotIn('候选', json.dumps(summary, ensure_ascii=False))
        self.assertLess((self.store.root / 'status.json').stat().st_size, 1024)
