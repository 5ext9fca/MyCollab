"""计划日期、结束顺序硬约束与原依赖图的甘特投影。"""
from datetime import date
from unittest.mock import patch
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import Mission, MissionDependency
from . import utils
from .test_concurrency_features import run_concurrently


class ScheduleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner')
        self.other = User.objects.create_user('other')
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def mission(self, **kwargs):
        return services.create_mission(actor=self.owner, title='任务', **kwargs)

    def test_dates_optional_same_day_strict_and_db_constraint(self):
        for start, end in [(None, None), ('2026-10-01', None), (None, '2026-10-01'), ('2026-10-01', '2026-10-01')]:
            m = self.mission(planned_start_date=start, planned_end_date=end)
            self.assertEqual(m.planned_start_date.isoformat() if m.planned_start_date else None, start)
        for start, end in [('2026-10-02', '2026-10-01'), ('20261001', None), ('2026-02-30', None)]:
            with self.assertRaises(ValidationFailure):
                self.mission(planned_start_date=start, planned_end_date=end)
        m = self.mission()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Mission.objects.filter(pk=m.pk).update(planned_start_date='2026-10-02', planned_end_date='2026-10-01')
        response = self.client.post('/api/missions/', {'title': '任务', 'planned_start_date': '20261001'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_dates_permissions_freeze_event_and_future_claim(self):
        m = self.mission(planned_start_date='2030-01-01', planned_end_date='2030-01-03')
        with self.assertRaises(PermissionDenied):
            utils.update(self.other, m, {'planned_end_date': '2030-01-04'})
        utils.claim(self.other, m)
        m = utils.update(self.owner, m, {'planned_end_date': None})
        self.assertTrue(m.events.filter(action='schedule_changed').exists())
        utils.submit(self.other, m)
        with self.assertRaises(ConflictError):
            utils.update(self.owner, m, {'planned_end_date': '2030-01-04'})

    def test_dependency_end_order_both_directions_and_new_edge(self):
        before = self.mission(planned_end_date='2026-10-10')
        after = self.mission(planned_start_date='2026-10-01', planned_end_date='2026-10-09')
        with self.assertRaises(ConflictError) as error:
            services.add_dependency(actor=self.owner, mission_id=after.pk, prerequisite_id=before.pk, expected_version=after.version)
        self.assertEqual(error.exception.code, 'schedule_dependency_conflict')
        after = utils.update(self.owner, after, {'planned_end_date': '2026-10-10'})
        services.add_dependency(actor=self.owner, mission_id=after.pk, prerequisite_id=before.pk, expected_version=after.version)
        with self.assertRaises(ConflictError):
            utils.update(self.owner, after, {'planned_end_date': '2026-10-09'})
        with self.assertRaises(ConflictError):
            utils.update(self.owner, before, {'planned_end_date': '2026-10-11'})
        before.refresh_from_db(); self.assertEqual(before.planned_end_date, date(2026, 10, 10))
        after = utils.update(self.owner, after, {'planned_end_date': '2026-10-12'})
        utils.update(self.owner, before, {'planned_end_date': '2026-10-11'})
        state = services.derived_state(after)
        self.assertTrue(state['is_blocked'])
        self.assertEqual(state['dependency_date_conflict_ids'], [str(before.pk)])
        # 缺少结束日期不伪造日期，但实际提交仍受前置 Done 约束。
        utils.update(self.owner, after, {'planned_end_date': None})
        utils.claim(self.other, after)
        with self.assertRaises(ConflictError):
            utils.submit(self.other, after)

    def test_risks_use_hidden_prerequisites_and_milestone_changes_revision(self):
        milestone = services.create_milestone(actor=self.owner, name='交付', due_date=date(2026, 10, 11))
        before = self.mission(planned_end_date='2026-10-10')
        after = self.mission(planned_start_date='2026-10-05', planned_end_date='2026-10-12', milestone_id=milestone.pk)
        services.add_dependency(actor=self.owner, mission_id=after.pk, prerequisite_id=before.pk, expected_version=after.version)
        query = {'milestone': str(milestone.pk), 'context': 'false', 'date_from': '2026-10-01', 'date_to': '2026-10-31'}
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25)):
            first = self.client.get('/api/workspace/graph/', query).data
            row = first['nodes'][0]
            self.assertTrue(row['overdue']); self.assertTrue(row['beyond_milestone_due'])
            self.assertEqual(row['dependency_date_conflict_ids'], [str(before.pk)])
            self.assertEqual(row['unloaded_prerequisite_count'], 1)
            self.assertFalse(first['meta']['relationships_complete'])
            services.update_milestone(actor=self.owner, milestone_id=milestone.pk, expected_version=1, changes={'due_date': date(2026, 10, 15)})
            second = self.client.get('/api/workspace/graph/', query).data
            self.assertNotEqual(first['revision'], second['revision'])
            self.assertFalse(second['nodes'][0]['beyond_milestone_due'])
            utils.update(self.owner, before, {'planned_end_date': '2026-10-04'})
            third = self.client.get('/api/workspace/graph/', query).data
            self.assertNotEqual(second['revision'], third['revision'])
            self.assertEqual(third['nodes'][0]['dependency_date_conflict_ids'], [])
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 26)):
            fourth = self.client.get('/api/workspace/graph/', query).data
            self.assertNotEqual(third['revision'], fourth['revision'])

    def test_window_and_paginated_list_match_partial_undated_and_overlap(self):
        included = [self.mission(planned_start_date='2026-09-01', planned_end_date='2026-11-01'),
            self.mission(planned_start_date='2026-10-15'), self.mission(planned_end_date='2026-10-16'), self.mission()]
        self.mission(planned_start_date='2026-11-01', planned_end_date='2026-11-02')
        params = {'date_from': '2026-10-01', 'date_to': '2026-10-31'}
        for endpoint, key in [('/api/workspace/graph/', 'nodes'), ('/api/missions/', 'results')]:
            response = self.client.get(endpoint, params)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual({str(row['id']) for row in response.data[key]}, {str(m.pk) for m in included})
        for params in [{'date_from': '2026-10-01'}, {'date_from': '2026-10-31', 'date_to': '2026-10-01'}, {'date_from': '2026-01-01', 'date_to': '2027-01-02'}, {'date_from': '20261001', 'date_to': '2026-10-31'}]:
            self.assertEqual(self.client.get('/api/workspace/graph/', params).status_code, 400)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25)):
            meta = self.client.get('/api/workspace/graph/').data['meta']
            self.assertEqual(meta['date_from'], '2026-10-11'); self.assertEqual(meta['date_to'], '2026-12-06')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/workspace/graph/').status_code, 403)

    def test_done_cancelled_not_overdue_and_same_day_no_start_warning(self):
        before = self.mission(planned_end_date='2026-01-01')
        after = self.mission(planned_start_date='2026-01-01', planned_end_date='2026-01-01')
        services.add_dependency(actor=self.owner, mission_id=after.pk, prerequisite_id=before.pk, expected_version=1)
        self.assertEqual(services.derived_state(after)['dependency_date_conflict_ids'], [])
        utils.claim(self.owner, before); utils.submit(self.owner, before); utils.review(self.owner, before)
        self.assertFalse(services.derived_state(utils.fresh(before))['overdue'])
        utils.cancel(self.owner, after)
        self.assertFalse(services.derived_state(utils.fresh(after))['overdue'])


class ScheduleConcurrencyTests(TransactionTestCase):
    def test_date_change_and_dependency_cannot_violate_end_order(self):
        owner = User.objects.create_user('owner')
        a = services.create_mission(actor=owner, title='前置', planned_end_date='2026-10-10')
        b = services.create_mission(actor=owner, title='下游', planned_end_date='2026-10-11')
        results = run_concurrently(
            lambda: services.add_dependency(actor=owner, mission_id=b.pk, prerequisite_id=a.pk, expected_version=1),
            lambda: services.update_mission(actor=owner, mission_id=a.pk, expected_version=1, changes={'planned_end_date': '2026-10-12'}),
        )
        self.assertEqual(list(results.values()).count('ok'), 1, results)
        a.refresh_from_db(); b.refresh_from_db()
        if MissionDependency.objects.exists():
            self.assertLessEqual(a.planned_end_date, b.planned_end_date)
