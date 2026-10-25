from unittest.mock import patch
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from accounts.models import User
from common.exceptions import ConflictError
from missions import services
from missions.models import Mission
from notifications.models import Notification
from . import utils


class BulkUpdateTests(TransactionTestCase):
    def setUp(self):
        self.a = User.objects.create_user('a')
        self.b = User.objects.create_user('b')
        self.m = services.create_mission(actor=self.a, title='我的', reviewer_id=self.b.pk)
        self.other = services.create_mission(actor=self.b, title='别人的')
        self.client = APIClient(); self.client.force_authenticate(self.a)

    def send(self, items=None, changes=None):
        return self.client.post('/api/missions/bulk-update/', {'items': items if items is not None else [{'id': str(self.m.pk), 'expected_version': utils.version_of(self.m)}], 'changes': changes if changes is not None else {'priority': 'P0'}}, format='json')

    def test_mixed_results_freeze_conflict_notifications_and_noop(self):
        response = self.send(items=[{'id': str(m.pk), 'expected_version': 1} for m in [self.m, self.other]])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['succeeded_count'], 1); self.assertEqual(response.data['failed_count'], 1)
        self.assertEqual(response.data['results'][1]['status'], 403)
        self.assertEqual(Notification.objects.filter(kind='plan_changed', recipient=self.b).count(), 1)
        self.assertEqual(self.send().data['results'][0]['mission']['version'], 3)
        self.assertEqual(Notification.objects.filter(kind='plan_changed').count(), 1)
        stale = self.send(items=[{'id': str(self.m.pk), 'expected_version': 1}])
        self.assertEqual(stale.data['results'][0]['error']['code'], 'version_conflict')
        utils.claim(self.b, self.m); utils.submit(self.b, self.m)
        self.assertEqual(self.send().data['results'][0]['error']['code'], 'mission_frozen')

    def test_illegal_whole_input_writes_nothing(self):
        for changes in [{}, {'status': 'Done'}, {'priority': None}, {'planned_end_date': '20261025'}, {'milestone': 'invalid'}, {'planned_start_date': '2026-11-01', 'planned_end_date': '2026-10-01'}]:
            self.assertEqual(self.send(changes=changes).status_code, 400)
        for items in [[], [{'id': str(self.m.pk), 'expected_version': True}], [{'id': str(self.m.pk), 'expected_version': 1}] * 2]:
            self.assertEqual(self.send(items=items).status_code, 400)
        self.assertEqual(utils.version_of(self.m), 1)
        self.assertFalse(Notification.objects.exists())

    def test_omission_preserves_null_clears_and_closed_milestone_fails(self):
        milestone = services.create_milestone(actor=self.a, name='目标')
        utils.update(self.a, self.m, {'milestone': milestone.pk, 'planned_end_date': '2026-11-01'})
        self.send(changes={'priority': 'P1'})
        self.m.refresh_from_db(); self.assertEqual(self.m.milestone_id, milestone.pk); self.assertIsNotNone(self.m.planned_end_date)
        self.send(changes={'milestone': None, 'planned_end_date': None})
        self.m.refresh_from_db(); self.assertIsNone(self.m.milestone_id); self.assertIsNone(self.m.planned_end_date)
        services.transition_milestone(actor=self.a, milestone_id=milestone.pk, status='Cancelled', expected_version=1, reason='取消')
        self.assertFalse(self.send(changes={'milestone': str(milestone.pk)}).data['results'][0]['success'])

    def test_schedule_original_order_and_partial_commits(self):
        downstream = services.create_mission(actor=self.a, title='下游', planned_end_date='2026-10-26')
        utils.update(self.a, self.m, {'planned_end_date': '2026-10-25'})
        services.add_dependency(actor=self.a, mission_id=downstream.pk, prerequisite_id=self.m.pk, expected_version=1)
        items = [{'id': str(m.pk), 'expected_version': utils.version_of(m)} for m in [self.m, downstream]]
        response = self.send(items=items, changes={'planned_end_date': '2026-11-01'})
        self.assertEqual(response.data['results'][0]['error']['code'], 'schedule_dependency_conflict')
        self.assertTrue(response.data['results'][1]['success'])
        self.assertTrue(self.send(changes={'planned_end_date': '2026-11-01'}).data['results'][0]['success'])

    def test_unknown_exception_is_not_hidden_and_prior_commit_survives(self):
        second = services.create_mission(actor=self.a, title='第二项')
        original = services.update_mission
        def operation(**kwargs):
            if kwargs['mission_id'] == second.pk:
                raise RuntimeError('未知程序错误')
            return original(**kwargs)
        with patch('missions.services.update_mission', side_effect=operation):
            with self.assertRaises(RuntimeError):
                services.bulk_update_missions(actor=self.a, payload={'items': [{'id': str(m.pk), 'expected_version': 1} for m in [self.m, second]], 'changes': {'priority': 'P0'}})
        self.m.refresh_from_db(); self.assertEqual(self.m.priority, 'P0')
        self.assertEqual(utils.version_of(second), 1)

    def test_concurrent_single_edit_does_not_get_overwritten(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections, connections
        barrier = Barrier(2)
        def bulk():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return services.bulk_update_missions(actor=self.a, payload={'items': [{'id': str(self.m.pk), 'expected_version': 1}], 'changes': {'priority': 'P0'}})['results'][0]['success']
            finally:
                connections.close_all()
        def single():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                services.update_mission(actor=self.a, mission_id=self.m.pk, expected_version=1, changes={'priority': 'P1'})
                return True
            except ConflictError:
                return False
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            left = pool.submit(bulk); right = pool.submit(single)
            self.assertEqual(sum([left.result(timeout=15), right.result(timeout=15)]), 1)
        self.assertEqual(utils.version_of(self.m), 2)
