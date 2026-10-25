from datetime import date
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User
from missions import services
from missions.models import Mission
from missions.my_work import work_query
from . import utils


class MyWorkTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user('a', is_staff=True)
        self.b = User.objects.create_user('b')
        self.c = User.objects.create_user('c')
        self.client = APIClient(); self.client.force_authenticate(self.a)
        self.today = date(2026, 10, 25)

    def test_current_rejection_review_and_admin_personal_scope(self):
        m = services.create_mission(actor=self.a, title='任务', reviewer_id=self.c.pk)
        utils.claim(self.b, m); utils.submit(self.b, m)
        self.assertEqual(work_query(self.a, 'review', self.today).count(), 0)
        self.assertEqual(work_query(self.c, 'review', self.today).count(), 1)
        utils.review(self.c, m, decision='reject')
        self.assertEqual(work_query(self.b, 'returned', self.today).count(), 1)
        utils.submit(self.b, m)
        self.assertEqual(work_query(self.b, 'returned', self.today).count(), 0)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25))
    def test_full_counts_pagination_dates_and_strict_category(self, _):
        for i in range(24):
            services.create_mission(actor=self.a, title=str(i), planned_end_date=self.today)
        for end in ['2026-10-24', '2026-10-28', '2026-10-29', None]:
            services.create_mission(actor=self.a, title=str(end), planned_end_date=end)
        summary = self.client.get('/api/my-work/summary/').data
        self.assertEqual(summary['counts']['due_soon'], 25)
        self.assertEqual(summary['counts']['overdue'], 1)
        page = self.client.get('/api/my-work/missions/?category=due_soon').data
        self.assertEqual(page['count'], 25); self.assertEqual(len(page['results']), 20)
        self.assertEqual(self.client.get('/api/my-work/missions/').status_code, 400)
        self.assertEqual(self.client.get('/api/my-work/missions/?category=review&reviewer=me').status_code, 400)

    def test_ready_requires_edge_and_child_hint_remains(self):
        m = services.create_mission(actor=self.a, title='下游')
        pre = services.create_mission(actor=self.a, title='前置')
        utils.claim(self.b, m)
        self.assertEqual(work_query(self.b, 'unblocked', self.today).count(), 0)
        services.add_dependency(actor=self.a, mission_id=m.pk, prerequisite_id=pre.pk, expected_version=utils.version_of(m))
        utils.claim(self.b, pre); utils.submit(self.b, pre); utils.review(self.a, pre)
        services.create_mission(actor=self.a, title='子任务', parent_id=m.pk)
        self.assertEqual(work_query(self.b, 'unblocked', self.today).count(), 1)
        self.assertTrue(services.derived_state(utils.fresh(m))['unfinished_child_ids'])

    def test_revalidation_roles_overlap_and_reopen_clears_historical_return(self):
        pre = services.create_mission(actor=self.a, title='前置')
        m = services.create_mission(actor=self.a, title='下游', reviewer_id=self.c.pk, planned_end_date=self.today)
        services.add_dependency(actor=self.a, mission_id=m.pk, prerequisite_id=pre.pk, expected_version=1)
        utils.claim(self.b, pre); utils.submit(self.b, pre); utils.review(self.a, pre)
        utils.claim(self.b, m); utils.submit(self.b, m)
        self.assertEqual(work_query(self.c, 'review', self.today).count(), 1)
        self.assertEqual(work_query(self.c, 'due_soon', self.today).count(), 1)
        utils.review(self.c, m, decision='reject'); utils.submit(self.b, m); utils.review(self.c, m)
        services.reopen_mission(actor=self.a, mission_id=pre.pk, reason='修复', expected_version=utils.version_of(pre))
        self.assertEqual(work_query(self.a, 'revalidation', self.today).count(), 1)
        self.assertEqual(work_query(self.c, 'revalidation', self.today).count(), 1)
        self.assertEqual(work_query(self.b, 'revalidation', self.today).count(), 0)
        services.reopen_mission(actor=self.a, mission_id=m.pk, reason='修复', expected_version=utils.version_of(m))
        self.assertEqual(work_query(self.b, 'returned', self.today).count(), 0)
        self.assertEqual(work_query(self.c, 'due_soon', self.today).count(), 1)
        from datetime import timedelta
        self.assertEqual(work_query(self.c, 'overdue', self.today + timedelta(days=1)).count(), 1)
