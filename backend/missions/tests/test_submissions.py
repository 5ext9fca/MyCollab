import importlib

from django.apps import apps as global_apps
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import (
    MilestoneStatus,
    Mission,
    MissionStatus,
    MissionSubmission,
    SubmissionBuildReference,
    SubmissionOutcome,
)

from . import utils


def make_done(creator, worker, mission, reviewer=None):
    utils.claim(worker, mission)
    mission = utils.submit(worker, mission)
    return utils.review(reviewer or creator, mission, decision="accept")


class ReviewerTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")
        self.admin = User.objects.create_user("admin", password="pw", is_staff=True)

    def test_reviewer_defaults_to_creator(self):
        mission = services.create_mission(actor=self.alice, title="t")
        self.assertEqual(mission.reviewer_id, self.alice.id)

    def test_explicit_reviewer_and_three_distinct_roles(self):
        mission = services.create_mission(
            actor=self.alice, title="t", reviewer_id=self.carol.id
        )
        utils.claim(self.bob, mission)
        utils.submit(self.bob, mission)
        # Creator is not the reviewer, so the creator cannot accept.
        with self.assertRaises(PermissionDenied):
            utils.review(self.alice, mission, decision="accept")
        mission = utils.review(self.carol, mission, decision="accept")
        self.assertEqual(mission.status, MissionStatus.DONE)

    def test_admin_can_review_and_actor_is_recorded(self):
        mission = services.create_mission(actor=self.alice, title="t", reviewer_id=self.carol.id)
        mission = utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission)
        utils.review(self.admin, mission, decision="accept", comment="管理员通过")
        submission = MissionSubmission.objects.get(pk=mission.current_submission_id)
        self.assertEqual(submission.reviewed_by_id, self.admin.id)

    def test_invalid_reviewer_rejected(self):
        inactive = User.objects.create_user("inactive", password="pw", is_active=False)
        with self.assertRaises(ValidationFailure):
            services.create_mission(actor=self.alice, title="t", reviewer_id=inactive.id)

    def test_submit_requires_active_reviewer(self):
        mission = services.create_mission(actor=self.alice, title="t")
        utils.claim(self.bob, mission)
        mission.reviewer = None
        mission.save(update_fields=["reviewer"])
        with self.assertRaises(ConflictError) as ctx:
            utils.submit(self.bob, mission)
        self.assertEqual(ctx.exception.code, "reviewer_missing")

    def test_transfer_review(self):
        mission = services.create_mission(actor=self.alice, title="t")
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission)
        mission = services.transfer_review(
            actor=self.alice,
            mission_id=mission.id,
            new_reviewer_id=self.carol.id,
            reason="负责人休假",
            expected_version=utils.version_of(mission),
        )
        self.assertEqual(mission.reviewer_id, self.carol.id)
        self.assertTrue(mission.events.filter(action="review_transferred").exists())
        # The old reviewer (alice) can no longer review.
        with self.assertRaises(PermissionDenied):
            utils.review(self.alice, mission, decision="accept")
        mission = utils.review(self.carol, mission, decision="accept")
        self.assertEqual(mission.status, MissionStatus.DONE)

    def test_transfer_requires_reason_and_submitted_status(self):
        mission = services.create_mission(actor=self.alice, title="t")
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission)
        with self.assertRaises(ValidationFailure):
            services.transfer_review(
                actor=self.alice,
                mission_id=mission.id,
                new_reviewer_id=self.carol.id,
                reason="",
                expected_version=utils.version_of(mission),
            )


class SubmissionTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")

    def _claimed(self, **kwargs):
        mission = services.create_mission(actor=self.alice, title="t", **kwargs)
        return utils.claim(self.bob, mission)

    def test_submit_creates_immutable_submission_and_history(self):
        mission = self._claimed()
        mission = utils.submit(self.bob, mission, description="v1")
        first = MissionSubmission.objects.get(pk=mission.current_submission_id)
        self.assertEqual(first.description, "v1")
        self.assertEqual(first.outcome, SubmissionOutcome.PENDING)
        self.assertEqual(mission.result, "v1")

        mission = utils.review(self.alice, mission, decision="reject", comment="再改")
        self.assertEqual(MissionSubmission.objects.get(pk=first.id).outcome, SubmissionOutcome.REJECTED)

        mission = utils.submit(self.bob, mission, description="v2")
        second = MissionSubmission.objects.get(pk=mission.current_submission_id)
        self.assertNotEqual(first.id, second.id)
        # Old round is preserved unchanged.
        self.assertEqual(MissionSubmission.objects.get(pk=first.id).description, "v1")
        self.assertEqual(mission.submissions.count(), 2)

    def test_evidence_required(self):
        mission = self._claimed()
        with self.assertRaises(ValidationFailure):
            services.submit_mission(
                actor=self.bob,
                mission_id=mission.id,
                description="只有描述",
                expected_version=utils.version_of(mission),
            )
        # A manual verification note alone is enough.
        mission = services.submit_mission(
            actor=self.bob,
            mission_id=mission.id,
            description="文档任务",
            verification_description="人工检查了内容",
            expected_version=utils.version_of(mission),
        )
        self.assertEqual(mission.status, MissionStatus.SUBMITTED)

    def test_source_reference_validation(self):
        mission = self._claimed()
        with self.assertRaises(ValidationFailure):
            services.submit_mission(
                actor=self.bob,
                mission_id=mission.id,
                description="x",
                source_references=[{"provider": "Git", "repository": "r", "revision": ""}],
                expected_version=utils.version_of(mission),
            )
        with self.assertRaises(ValidationFailure):
            services.submit_mission(
                actor=self.bob,
                mission_id=mission.id,
                description="x",
                source_references=[
                    {"provider": "Git", "repository": "r", "revision": "abc", "browse_url": "ftp://x"}
                ],
                expected_version=utils.version_of(mission),
            )

    def test_build_accept_requires_succeeded_and_selected_reference(self):
        mission = self._claimed()
        mission = utils.submit(
            self.bob,
            mission,
            description="带构建",
            build_references=[
                {
                    "provider": "Jenkins",
                    "build_id": "2026.10.12.42",
                    "platform": "Windows",
                    "status": "Failed",
                },
                {
                    "provider": "Jenkins",
                    "build_id": "2026.10.12.43",
                    "platform": "Windows",
                    "status": "Succeeded",
                },
            ],
        )
        submission = MissionSubmission.objects.get(pk=mission.current_submission_id)
        succeeded = submission.build_references.get(status="Succeeded")

        # Without selecting a build, acceptance is rejected.
        with self.assertRaises(ValidationFailure):
            utils.review(self.alice, mission, decision="accept", comment="")

        mission = utils.review(
            self.alice,
            mission,
            decision="accept",
            comment="选择成功构建",
            verified_build_reference_id=succeeded.id,
        )
        submission.refresh_from_db()
        self.assertEqual(submission.outcome, SubmissionOutcome.ACCEPTED)
        self.assertEqual(submission.verified_build_reference_id, succeeded.id)

    def test_failed_only_build_cannot_be_accepted(self):
        mission = self._claimed()
        mission = utils.submit(
            self.bob,
            mission,
            description="失败构建",
            build_references=[
                {
                    "provider": "Jenkins",
                    "build_id": "1",
                    "platform": "Windows",
                    "status": "Failed",
                }
            ],
        )
        submission = MissionSubmission.objects.get(pk=mission.current_submission_id)
        failed = submission.build_references.first()
        with self.assertRaises(ConflictError) as ctx:
            utils.review(
                self.alice,
                mission,
                decision="accept",
                comment="",
                verified_build_reference_id=failed.id,
            )
        self.assertEqual(ctx.exception.code, "build_not_succeeded")

    def test_cross_submission_build_reference_rejected(self):
        mission_a = self._claimed()
        mission_a = utils.submit(
            self.bob,
            mission_a,
            description="a",
            build_references=[{"provider": "J", "build_id": "1", "platform": "Win", "status": "Succeeded"}],
        )
        mission_b = utils.claim(self.carol, services.create_mission(actor=self.alice, title="b"))
        mission_b = utils.submit(
            self.carol,
            mission_b,
            description="b",
            build_references=[{"provider": "J", "build_id": "2", "platform": "Win", "status": "Succeeded"}],
        )
        other_build = MissionSubmission.objects.get(
            pk=mission_b.current_submission_id
        ).build_references.first()
        with self.assertRaises(ValidationFailure):
            utils.review(
                self.alice,
                mission_a,
                decision="accept",
                comment="",
                verified_build_reference_id=other_build.id,
            )

    def test_duplicate_or_stale_review_rejected(self):
        mission = self._claimed()
        mission = utils.submit(self.bob, mission)
        submission_id = mission.current_submission_id
        mission = utils.review(self.alice, mission, decision="accept")
        # Re-reviewing the accepted submission is rejected (no longer Submitted).
        with self.assertRaises(ConflictError):
            services.review_mission(
                actor=self.alice,
                mission_id=mission.id,
                submission_id=submission_id,
                decision="accept",
                comment="x",
                expected_version=utils.version_of(mission),
            )

    def test_submission_listing_and_is_legacy_not_client_set(self):
        mission = self._claimed()
        utils.submit(self.bob, mission, description="r")
        client = APIClient()
        client.force_authenticate(self.alice)
        response = client.post(
            f"/api/missions/{mission.id}/submit/",
            {"description": "again", "is_legacy": True, "expected_version": utils.version_of(mission)},
            format="json",
        )
        # Not the assignee anymore? bob is the assignee; alice is not.
        self.assertEqual(response.status_code, 403)

        listing = client.get(f"/api/missions/{mission.id}/submissions/")
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(all(not row["is_legacy"] for row in listing.json()["results"]))


class ReopenTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")

    def _done(self, **kwargs):
        mission = services.create_mission(actor=self.alice, title="t", **kwargs)
        utils.claim(self.bob, mission)
        utils.submit(self.bob, mission)
        return utils.review(self.alice, mission, decision="accept")

    def test_reopen_requires_reason_and_done(self):
        mission = self._done()
        with self.assertRaises(ValidationFailure):
            services.reopen_mission(
                actor=self.alice,
                mission_id=mission.id,
                reason="",
                expected_version=utils.version_of(mission),
            )
        open_mission = services.create_mission(actor=self.alice, title="o")
        with self.assertRaises(ConflictError):
            services.reopen_mission(
                actor=self.alice,
                mission_id=open_mission.id,
                reason="x",
                expected_version=utils.version_of(open_mission),
            )

    def test_reopen_preserves_history_and_clears_current(self):
        mission = self._done()
        submission_id = mission.current_submission_id
        mission = services.reopen_mission(
            actor=self.alice,
            mission_id=mission.id,
            reason="回归",
            expected_version=utils.version_of(mission),
        )
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)
        self.assertEqual(mission.assignee_id, self.bob.id)
        self.assertIsNone(mission.current_submission_id)
        preserved = MissionSubmission.objects.get(pk=submission_id)
        self.assertEqual(preserved.outcome, SubmissionOutcome.ACCEPTED)
        self.assertTrue(mission.events.filter(action="reopened").exists())

    def test_reopen_with_inactive_assignee_returns_to_open(self):
        mission = self._done()
        self.bob.is_active = False
        self.bob.save(update_fields=["is_active"])
        mission = services.reopen_mission(
            actor=self.alice,
            mission_id=mission.id,
            reason="接手",
            expected_version=utils.version_of(mission),
        )
        self.assertEqual(mission.status, MissionStatus.OPEN)
        self.assertIsNone(mission.assignee_id)

    def test_reopen_rejected_when_ancestor_done(self):
        parent = services.create_mission(actor=self.alice, title="p")
        child = services.create_mission(actor=self.alice, title="c", parent_id=parent.id)
        # Complete child then parent.
        utils.claim(self.bob, child)
        utils.submit(self.bob, child)
        utils.review(self.alice, child, decision="accept")
        utils.claim(self.carol, parent)
        utils.submit(self.carol, parent)
        utils.review(self.alice, parent, decision="accept")

        child = utils.fresh(child)
        with self.assertRaises(ConflictError) as ctx:
            services.reopen_mission(
                actor=self.alice,
                mission_id=child.id,
                reason="x",
                expected_version=utils.version_of(child),
            )
        self.assertEqual(ctx.exception.code, "ancestor_done")

    def test_reopen_rejected_when_milestone_closed(self):
        milestone = services.create_milestone(actor=self.alice, name="m")
        milestone = services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.ACTIVE,
            expected_version=milestone.version,
        )
        mission = services.create_mission(actor=self.alice, title="t", milestone_id=milestone.id)
        utils.claim(self.bob, mission)
        utils.submit(self.bob, mission)
        mission = utils.review(self.alice, mission, decision="accept")
        services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.COMPLETED,
            expected_version=milestone.version,
        )
        with self.assertRaises(ConflictError) as ctx:
            services.reopen_mission(
                actor=self.alice,
                mission_id=mission.id,
                reason="x",
                expected_version=utils.version_of(mission),
            )
        self.assertEqual(ctx.exception.code, "milestone_closed")


class TransferReopenApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")
        self.client = APIClient()

    def _submitted(self):
        mission = services.create_mission(actor=self.alice, title="t")
        utils.claim(self.bob, mission)
        return utils.submit(self.bob, mission)

    def test_transfer_review_endpoint(self):
        mission = self._submitted()
        self.client.force_authenticate(self.alice)
        response = self.client.post(
            f"/api/missions/{mission.id}/transfer-review/",
            {
                "new_reviewer_id": self.carol.id,
                "reason": "休假",
                "expected_version": utils.version_of(mission),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["reviewer"]["username"], "carol")

    def test_reopen_endpoint(self):
        mission = self._submitted()
        utils.review(self.alice, mission, decision="accept")
        self.client.force_authenticate(self.alice)
        response = self.client.post(
            f"/api/missions/{mission.id}/reopen/",
            {"reason": "回归", "expected_version": utils.version_of(mission)},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "InProgress")
        self.assertIsNone(body["current_submission"])

    def test_review_endpoint_selects_build(self):
        mission = services.create_mission(actor=self.alice, title="t")
        utils.claim(self.bob, mission)
        mission = utils.submit(
            self.bob,
            mission,
            description="带构建",
            build_references=[
                {"provider": "Jenkins", "build_id": "9", "platform": "Windows", "status": "Succeeded"}
            ],
        )
        submission = MissionSubmission.objects.get(pk=mission.current_submission_id)
        build = submission.build_references.first()
        self.client.force_authenticate(self.alice)
        response = self.client.post(
            f"/api/missions/{mission.id}/review/",
            {
                "submission_id": str(submission.id),
                "decision": "accept",
                "comment": "选择构建",
                "verified_build_reference_id": str(build.id),
                "expected_version": utils.version_of(mission),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "Done")


class LegacyBackfillTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")

    def test_backfill_imports_legacy_submissions_without_fabricating_evidence(self):
        # Build a mission, then strip it down to look like pre-migration data.
        mission = services.create_mission(actor=self.alice, title="old")
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission, description="旧成果")
        MissionSubmission.objects.filter(mission=mission).delete()
        Mission.objects.filter(pk=mission.id).update(
            reviewer=None, current_submission=None, status="Done", result="旧成果"
        )

        backfill_module = importlib.import_module(
            "missions.migrations.0004_backfill_legacy"
        )
        backfill_module.backfill(global_apps, None)

        mission.refresh_from_db()
        self.assertEqual(mission.reviewer_id, self.alice.id)
        submission = MissionSubmission.objects.get(mission=mission)
        self.assertTrue(submission.is_legacy)
        self.assertEqual(submission.description, "旧成果")
        self.assertEqual(submission.outcome, SubmissionOutcome.ACCEPTED)
        # A reviewer identity / time must not be fabricated.
        self.assertIsNone(submission.reviewed_by_id)
        self.assertIsNone(submission.reviewed_at)
        self.assertEqual(submission.reviewer_snapshot_id, self.alice.id)
        self.assertEqual(mission.status, MissionStatus.DONE)

    def test_backfill_pending_for_submitted(self):
        mission = services.create_mission(actor=self.alice, title="old")
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission, description="待验收旧成果")
        MissionSubmission.objects.filter(mission=mission).delete()
        Mission.objects.filter(pk=mission.id).update(reviewer=None, current_submission=None)

        backfill_module = importlib.import_module("missions.migrations.0004_backfill_legacy")
        backfill_module.backfill(global_apps, None)

        submission = MissionSubmission.objects.get(mission=mission)
        self.assertEqual(submission.outcome, SubmissionOutcome.PENDING)
        self.assertTrue(submission.is_legacy)

    def test_legacy_pending_can_be_reviewed_with_manual_note(self):
        mission = services.create_mission(actor=self.alice, title="old")
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission, description="旧待验收成果")
        MissionSubmission.objects.filter(mission=mission).delete()
        Mission.objects.filter(pk=mission.id).update(reviewer=None, current_submission=None)
        backfill_module = importlib.import_module("missions.migrations.0004_backfill_legacy")
        backfill_module.backfill(global_apps, None)

        mission = Mission.objects.get(pk=mission.id)
        mission = utils.review(self.alice, mission, decision="accept")
        self.assertEqual(mission.status, MissionStatus.DONE)
        self.assertTrue(mission.events.filter(action="review_approved").exists())
