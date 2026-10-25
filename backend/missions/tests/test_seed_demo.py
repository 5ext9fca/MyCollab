from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from missions import services
from missions.models import (
    Milestone,
    Mission,
    MissionDependency,
    MissionStatus,
    SubmissionOutcome,
)


class SeedDemoCommandTests(TestCase):
    """`seed_demo` builds a coherent demo dataset through the service layer."""

    def test_seed_demo_creates_consistent_sample_data(self):
        call_command("seed_demo")

        self.assertTrue(User.objects.filter(username="alice").exists())
        self.assertGreaterEqual(Milestone.objects.count(), 2)
        self.assertTrue(MissionDependency.objects.exists())

        # A prerequisite is still running, so its dependent shows as blocked.
        online = Mission.objects.get(title="实现基础联机同步")
        state = services.derived_state(online)
        self.assertTrue(state["has_unresolved_prerequisites"])
        self.assertTrue(state["is_blocked"])

        # A finished task carries immutable evidence and an accepted review.
        done = Mission.objects.get(title="搭建构建流水线", status=MissionStatus.DONE)
        submission = done.submissions.get()
        self.assertEqual(submission.outcome, SubmissionOutcome.ACCEPTED)
        self.assertTrue(submission.source_references.exists())
        self.assertTrue(submission.build_references.exists())
        self.assertIsNotNone(submission.verified_build_reference_id)

    def test_seed_demo_is_idempotent_without_reset(self):
        call_command("seed_demo")
        count = Mission.objects.count()
        call_command("seed_demo")
        self.assertEqual(Mission.objects.count(), count)

    def test_seed_demo_reset_rebuilds_sample_data(self):
        call_command("seed_demo")
        alice = User.objects.get(username="alice")
        services.create_mission(actor=alice, title="临时任务")

        call_command("seed_demo", reset=True)

        self.assertFalse(Mission.objects.filter(title="临时任务").exists())
        self.assertTrue(Mission.objects.filter(title="实现角色移动系统").exists())

    def test_work_categories_and_collaboration_scenarios(self):
        from django.utils import timezone
        from missions.my_work import work_query
        from missions.models import ProductionBatch, SavedMissionView
        from notifications.models import Notification, MissionSubscription

        call_command('seed_demo')
        alice = User.objects.get(username='alice')
        bob = User.objects.get(username='bob')
        self.assertTrue(alice.check_password('demo12345'))
        for category in ('review', 'due_soon', 'overdue', 'revalidation'):
            self.assertTrue(work_query(alice, category, timezone.localdate()).exists(), category)
        for category in ('returned', 'unblocked'):
            self.assertTrue(work_query(bob, category, timezone.localdate()).exists(), category)
        self.assertEqual(set(Mission.objects.values_list('status', flat=True)), set(MissionStatus.values))
        self.assertEqual(ProductionBatch.objects.get().items.count(), 3)
        self.assertEqual(SavedMissionView.objects.count(), 4)
        self.assertEqual(MissionSubscription.objects.count(), 2)
        self.assertTrue(Notification.objects.filter(read_at__isnull=False).exists())
        for kind in ('dependency_revalidation', 'dependency_unblocked', 'due_soon', 'overdue'):
            self.assertTrue(Notification.objects.filter(kind=kind).exists(), kind)
        count = Mission.objects.count()
        call_command('seed_demo', reset=True)
        self.assertEqual(Mission.objects.count(), count)
        self.assertEqual(ProductionBatch.objects.count(), 1)
        self.assertEqual(SavedMissionView.objects.count(), 4)
        self.assertEqual(User.objects.get(username='alice').pk, alice.pk)

    def test_reset_preserves_other_members_and_rejects_cross_references(self):
        from django.core.management.base import CommandError

        call_command('seed_demo')
        other = User.objects.create_user('independent', password='keep-password')
        own = services.create_mission(actor=other, title='保留独立任务')
        call_command('seed_demo', reset=True)
        self.assertTrue(Mission.objects.filter(pk=own.pk).exists())
        self.assertTrue(User.objects.get(pk=other.pk).check_password('keep-password'))
        demo = Mission.objects.filter(creator__username='alice', status='Open').first()
        own.refresh_from_db()
        services.add_dependency(actor=other, mission_id=own.pk, prerequisite_id=demo.pk,
                                expected_version=own.version)
        count = Mission.objects.count()
        with self.assertRaises(CommandError):
            call_command('seed_demo', reset=True)
        self.assertEqual(Mission.objects.count(), count)
        self.assertTrue(Mission.objects.filter(pk=demo.pk).exists())


    def test_reset_repairs_legacy_empty_password_and_preserves_custom_password(self):
        alice = User.objects.create(username='alice', password='')
        bob = User.objects.create_user('bob', password='custom-demo-password')
        call_command('seed_demo', reset=True)
        alice.refresh_from_db()
        bob.refresh_from_db()
        self.assertTrue(alice.check_password('demo12345'))
        self.assertTrue(bob.check_password('custom-demo-password'))
