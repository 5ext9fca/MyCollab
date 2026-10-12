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
        done = Mission.objects.get(status=MissionStatus.DONE)
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
