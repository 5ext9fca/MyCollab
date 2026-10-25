from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest.mock import patch
from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from accounts.models import User
from common.exceptions import ConflictError
from missions.services import create_mission
from notifications.models import Notification
from notifications.services import deliver, send_reminders, set_subscription


class NotificationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user('member')
        self.mission = create_mission(actor=self.user, title='任务', planned_end_date=date(2026, 10, 25))

    def parallel(self, operation):
        barrier = Barrier(2)
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: run(), range(2)))

    def test_subscription_first_write_has_one_winner(self):
        def operation():
            try:
                set_subscription(user=self.user, mission_id=self.mission.pk, mode='Follow', expected_version=0)
                return 'ok'
            except ConflictError as exc:
                return exc.code
        self.assertCountEqual(self.parallel(operation), ['ok', 'version_conflict'])

    def test_same_source_and_concurrent_reminders_are_unique(self):
        self.parallel(lambda: deliver(mission=self.mission, actor=None, kind='comment_created', source_key='comment:1:created'))
        self.assertEqual(Notification.objects.count(), 1)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25)):
            counts = self.parallel(send_reminders)
        self.assertEqual(sum(added for _, added in counts), 1)
        self.assertEqual(Notification.objects.filter(kind='due_soon').count(), 1)

    def test_reminder_rechecks_after_concurrent_cancel(self):
        from threading import Event
        from django.db import transaction
        from missions.services import _acquire_team_lock, cancel_mission
        reached = Event()
        real_lock = _acquire_team_lock
        def observed_lock():
            reached.set()
            real_lock()
        def run():
            close_old_connections()
            try:
                return send_reminders()
            finally:
                connections.close_all()
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25)):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    real_lock()
                    cancel_mission(actor=self.user, mission_id=self.mission.pk, expected_version=1)
                    with patch('missions.services._acquire_team_lock', side_effect=observed_lock):
                        future = pool.submit(run)
                        self.assertTrue(reached.wait(10))
                self.assertEqual(future.result(timeout=10)[1], 0)
        self.assertFalse(Notification.objects.exists())
