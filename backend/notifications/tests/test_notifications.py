from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from rest_framework.test import APIClient
from accounts.models import User
from missions import services as missions
from missions.models import Mission
from missions.tests import utils
from notifications.models import Notification
from notifications import services


class NotificationTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user('a')
        self.b = User.objects.create_user('b')
        self.c = User.objects.create_user('c')
        self.admin = User.objects.create_user('admin', is_staff=True)
        self.m = missions.create_mission(actor=self.a, title='任务', reviewer_id=self.c.pk)
        self.client = APIClient()
        self.client.force_authenticate(self.a)

    def subscription(self, user, mode):
        return services.set_subscription(user=user, mission_id=self.m.pk, mode=mode, expected_version=0)

    def test_lifecycle_mute_mandatory_and_transfer(self):
        self.subscription(self.c, 'Mute')
        utils.claim(self.b, self.m)
        self.assertFalse(Notification.objects.filter(recipient=self.c).exists())
        utils.submit(self.b, self.m)
        self.assertEqual(Notification.objects.filter(recipient=self.c, kind='submitted').count(), 1)
        utils.review(self.c, self.m, decision='reject')
        self.assertTrue(Notification.objects.filter(recipient=self.b, kind='review_rejected').exists())
        utils.submit(self.b, self.m)
        missions.transfer_review(actor=self.admin, mission_id=self.m.pk, new_reviewer_id=self.a.pk, reason='调整', expected_version=utils.version_of(self.m))
        self.assertTrue(Notification.objects.filter(recipient=self.a, kind='review_transferred').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.c, kind='review_transferred').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.b, actor=self.b).exists())

    def test_old_reviewer_follow_comments_and_deleted_text(self):
        self.subscription(self.b, 'Follow')
        comment = missions.create_comment(actor=self.a, mission_id=self.m.pk, content='私密正文不应保存')
        row = Notification.objects.get(recipient=self.b)
        self.assertEqual(row.payload, {'summary': '新增评论'})
        missions.delete_comment(actor=self.a, comment_id=comment.pk)
        self.assertTrue(Notification.objects.filter(pk=row.pk).exists())
        utils.claim(self.b, self.m); utils.submit(self.b, self.m)
        missions.transfer_review(actor=self.admin, mission_id=self.m.pk, new_reviewer_id=self.a.pk, reason='调整', expected_version=utils.version_of(self.m))
        self.assertTrue(Notification.objects.filter(recipient=self.c, kind='review_transferred').exists())

    def test_plan_coalescing_noop_inactive_and_rollback(self):
        utils.update(self.a, self.m, {'priority': 'P0', 'planned_end_date': '2026-11-10'})
        self.assertEqual(Notification.objects.filter(recipient=self.c, kind='plan_changed').count(), 1)
        utils.update(self.a, self.m, {'priority': 'P0'})
        self.assertEqual(Notification.objects.filter(kind='plan_changed').count(), 1)
        before = Notification.objects.count()
        with self.assertRaises(Exception):
            utils.update(self.a, self.m, {'priority': 'P1', 'milestone': '00000000-0000-0000-0000-000000000001'})
        self.assertEqual(Notification.objects.count(), before)
        self.c.is_active = False; self.c.save()
        missions.create_comment(actor=self.a, mission_id=self.m.pk, content='消息')
        self.assertFalse(Notification.objects.filter(kind='comment_created').exists())

    def test_read_ownership_atomic_idempotence_and_subscription_version(self):
        missions.create_comment(actor=self.b, mission_id=self.m.pk, content='消息')
        own = Notification.objects.get(recipient=self.a)
        other = Notification.objects.get(recipient=self.c)
        self.assertEqual(self.client.post('/api/notifications/read/', {'ids': [str(own.pk), str(other.pk)]}, format='json').status_code, 404)
        own.refresh_from_db(); self.assertIsNone(own.read_at)
        for count in [1, 0]:
            self.assertEqual(self.client.post('/api/notifications/read/', {'ids': [str(own.pk)]}, format='json').data['changed_count'], count)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f'/api/notifications/{own.pk}/').status_code, 404)
        url = f'/api/missions/{self.m.pk}/subscription/'
        self.assertEqual(self.client.put(url, {'mode': 'Mute', 'expected_version': 0}, format='json').status_code, 200)
        self.assertEqual(self.client.put(url, {'mode': 'Follow', 'expected_version': 0}, format='json').status_code, 409)
        self.assertEqual(self.client.put(url, {'mode': 'Follow', 'expected_version': 1, 'user': self.a.pk}, format='json').status_code, 400)

    def test_dependency_transitions_and_source_idempotence(self):
        pre = missions.create_mission(actor=self.a, title='前置')
        edge = missions.add_dependency(actor=self.a, mission_id=self.m.pk, prerequisite_id=pre.pk, expected_version=1)
        missions.remove_dependency(actor=self.a, mission_id=self.m.pk, dependency_id=edge.pk, expected_version=utils.version_of(self.m))
        self.assertEqual(Notification.objects.filter(kind='dependency_unblocked', recipient=self.c).count(), 1)
        missions.add_dependency(actor=self.a, mission_id=self.m.pk, prerequisite_id=pre.pk, expected_version=utils.version_of(self.m))
        utils.claim(self.b, pre); utils.submit(self.b, pre); utils.review(self.a, pre)
        utils.claim(self.b, self.m); utils.submit(self.b, self.m); utils.review(self.c, self.m)
        missions.reopen_mission(actor=self.a, mission_id=pre.pk, expected_version=utils.version_of(pre), reason='修复')
        self.assertEqual(Notification.objects.filter(kind='dependency_revalidation', recipient=self.c).count(), 1)
        event = pre.events.first()
        services.from_event(event); services.from_event(event)
        self.assertEqual(Notification.objects.filter(source_key=f'event:{event.pk}:reopened:{pre.pk}', recipient=self.b).count(), 1)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25))
    def test_deadline_boundaries_repeat_reschedule_and_command(self, _):
        for offset in [-1, 0, 3, 4]:
            missions.create_mission(actor=self.a, title=str(offset), planned_end_date=date(2026, 10, 25) + timedelta(days=offset))
        out = StringIO(); call_command('send_mission_reminders', stdout=out)
        self.assertIn('新增 3 条', out.getvalue())
        self.assertEqual(services.send_reminders()[1], 0)
        m = Mission.objects.get(title='0')
        utils.update(self.a, m, {'planned_end_date': '2026-10-26'})
        self.assertEqual(services.send_reminders()[1], 1)
        utils.update(self.a, m, {'planned_end_date': '2026-10-25'})
        self.assertEqual(services.send_reminders()[1], 0)
        utils.cancel(self.a, m)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 1)):
            services.send_reminders()
        self.assertFalse(Notification.objects.filter(mission=m, kind='overdue').exists())

    def test_partial_prerequisites_cancel_and_recurring_revalidation(self):
        first = missions.create_mission(actor=self.a, title='第一前置')
        second = missions.create_mission(actor=self.a, title='第二前置')
        for pre in [first, second]:
            missions.add_dependency(actor=self.a, mission_id=self.m.pk, prerequisite_id=pre.pk, expected_version=utils.version_of(self.m))
        utils.claim(self.b, first); utils.submit(self.b, first); utils.review(self.a, first)
        self.assertFalse(Notification.objects.filter(kind='dependency_unblocked').exists())
        utils.cancel(self.a, second)
        self.assertFalse(Notification.objects.filter(kind='dependency_unblocked').exists())
        edge = self.m.dependencies.get(prerequisite=second)
        missions.remove_dependency(actor=self.a, mission_id=self.m.pk, dependency_id=edge.pk, expected_version=utils.version_of(self.m))
        self.assertEqual(Notification.objects.filter(kind='dependency_unblocked', recipient=self.c).count(), 1)
        utils.claim(self.b, self.m); utils.submit(self.b, self.m); utils.review(self.c, self.m)
        for iteration in range(2):
            missions.reopen_mission(actor=self.a, mission_id=first.pk, reason='重新检查', expected_version=utils.version_of(first))
            for _ in range(2):
                missions.derived_state(utils.fresh(self.m))
            self.assertEqual(Notification.objects.filter(kind='dependency_revalidation', recipient=self.c).count(), iteration + 1)
            utils.submit(self.b, first); utils.review(self.a, first)

    def test_csrf_and_strict_subscription_version(self):
        client = APIClient(enforce_csrf_checks=True); client.force_login(self.a)
        url = f'/api/missions/{self.m.pk}/subscription/'
        self.assertEqual(client.put(url, {'mode': 'Mute', 'expected_version': 0}, format='json').status_code, 403)
        client.get('/api/auth/csrf/')
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.put(url, {'mode': 'Mute', 'expected_version': 0}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(client.put(url, {'mode': 'Follow', 'expected_version': True}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
