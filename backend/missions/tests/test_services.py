from django.test import TestCase

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import MissionPriority, MissionStatus, MissionType

from . import utils


class MissionServiceTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")

    def _mission(self, **kwargs):
        defaults = {"actor": self.alice, "title": "任务"}
        defaults.update(kwargs)
        return services.create_mission(**defaults)

    def test_create_defaults(self):
        mission = self._mission(tags=["Unity", "Gameplay"])
        self.assertEqual(mission.status, MissionStatus.OPEN)
        self.assertIsNone(mission.assignee_id)
        self.assertEqual(mission.version, 1)
        self.assertEqual(mission.type, MissionType.TASK)
        self.assertEqual(mission.priority, MissionPriority.P2)
        self.assertEqual(mission.reviewer_id, self.alice.id)
        self.assertIsNone(mission.milestone_id)
        self.assertEqual(
            set(mission.tags.values_list("name", flat=True)), {"Unity", "Gameplay"}
        )
        self.assertTrue(mission.events.filter(action="created").exists())

    def test_claim_sets_assignee_and_is_exclusive(self):
        mission = self._mission()
        mission = utils.claim(self.bob, mission)
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)
        self.assertEqual(mission.assignee_id, self.bob.id)
        self.assertEqual(mission.version, 2)
        with self.assertRaises(ConflictError):
            utils.claim(self.carol, mission)

    def test_release_returns_to_open(self):
        mission = self._mission()
        utils.claim(self.bob, mission)
        mission = utils.release(self.bob, mission)
        self.assertEqual(mission.status, MissionStatus.OPEN)
        self.assertIsNone(mission.assignee_id)
        with self.assertRaises(PermissionDenied):
            utils.release(self.carol, mission)

    def test_claim_requires_expected_version(self):
        mission = self._mission()
        with self.assertRaises(ConflictError) as ctx:
            services.claim_mission(actor=self.bob, mission_id=mission.id, expected_version=99)
        self.assertEqual(ctx.exception.code, "version_conflict")

    def test_submit_requires_assignee_result_and_complete_children(self):
        parent = self._mission()
        child = self._mission(parent_id=parent.id)
        utils.claim(self.bob, parent)

        with self.assertRaises(ValidationFailure):
            utils.submit(self.bob, parent, description="  ")
        with self.assertRaises(ConflictError):
            utils.submit(self.bob, parent, description="整合完成")
        with self.assertRaises(PermissionDenied):
            services.submit_mission(
                actor=self.carol,
                mission_id=parent.id,
                description="x",
                verification_description="人工验证",
                expected_version=utils.version_of(parent),
            )

        utils.claim(self.carol, child)
        utils.submit(self.carol, child, description="子任务完成")
        utils.review(self.alice, child, decision="accept")

        parent = utils.submit(self.bob, parent, description="整合完成")
        self.assertEqual(parent.status, MissionStatus.SUBMITTED)

    def test_cancelled_child_does_not_block_parent(self):
        parent = self._mission()
        child = self._mission(parent_id=parent.id)
        utils.claim(self.bob, parent)
        utils.cancel(self.alice, child, reason="范围调整")
        parent = utils.submit(self.bob, parent, description="完成")
        self.assertEqual(parent.status, MissionStatus.SUBMITTED)

    def test_review_approve_and_reject(self):
        mission = self._mission()
        utils.claim(self.bob, mission)
        utils.submit(self.bob, mission)
        with self.assertRaises(PermissionDenied):
            utils.review(self.bob, mission, decision="accept")

        mission = utils.review(self.alice, mission, decision="reject", comment="再改改")
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)

        utils.submit(self.bob, mission, description="成果v2")
        mission = utils.review(self.alice, mission, decision="accept")
        self.assertEqual(mission.status, MissionStatus.DONE)

    def test_cancel_child_requires_reason(self):
        parent = self._mission()
        child = self._mission(parent_id=parent.id)
        with self.assertRaises(ValidationFailure):
            utils.cancel(self.alice, child, reason="")
        child = utils.cancel(self.alice, child, reason="不需要了")
        self.assertEqual(child.status, MissionStatus.CANCELLED)

    def test_cancel_keeps_assignee(self):
        mission = self._mission()
        utils.claim(self.bob, mission)
        mission = utils.cancel(self.alice, mission)
        self.assertEqual(mission.status, MissionStatus.CANCELLED)
        self.assertEqual(mission.assignee_id, self.bob.id)

    def test_update_requires_creator_and_correct_version(self):
        mission = self._mission()
        with self.assertRaises(PermissionDenied):
            services.update_mission(
                actor=self.bob,
                mission_id=mission.id,
                expected_version=mission.version,
                changes={"title": "x"},
            )
        mission = services.update_mission(
            actor=self.alice,
            mission_id=mission.id,
            expected_version=mission.version,
            changes={"title": "v2"},
        )
        self.assertEqual(mission.title, "v2")
        with self.assertRaises(ConflictError):
            services.update_mission(
                actor=self.alice,
                mission_id=mission.id,
                expected_version=1,
                changes={"title": "v3"},
            )

    def test_update_frozen_when_submitted(self):
        mission = self._mission()
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission)
        with self.assertRaises(ConflictError):
            utils.update(self.alice, mission, changes={"title": "改不了"})

    def test_parent_rules(self):
        parent = self._mission()
        # Only the parent's creator or assignee may add children.
        with self.assertRaises(PermissionDenied):
            self._mission(actor=self.bob, parent_id=parent.id)

        child = self._mission(actor=self.alice, parent_id=parent.id)
        self.assertEqual(child.parent_id, parent.id)

        # A finished parent cannot receive new children.
        done_parent = self._mission(title="done")
        utils.claim(self.bob, done_parent)
        utils.submit(self.bob, done_parent)
        utils.review(self.alice, done_parent, decision="accept")
        with self.assertRaises(ConflictError):
            self._mission(actor=self.alice, parent_id=done_parent.id)

    def test_parent_cycle_is_rejected(self):
        a = self._mission(title="a")
        b = self._mission(title="b", parent_id=a.id)
        with self.assertRaises(ConflictError):
            services.update_mission(
                actor=self.alice,
                mission_id=a.id,
                expected_version=a.version,
                changes={"parent": b.id},
            )

    def test_allowed_actions(self):
        mission = self._mission()
        # Self-claim is allowed, so even the creator sees "claim".
        self.assertEqual(
            services.allowed_actions(self.alice, mission),
            ["claim", "edit", "cancel", "manage_dependencies", "create_child"],
        )
        # A bystander can only claim.
        self.assertEqual(services.allowed_actions(self.bob, mission), ["claim"])

        mission = utils.claim(self.bob, mission)
        self.assertIn("submit", services.allowed_actions(self.bob, mission))
        mission = utils.submit(self.bob, mission)
        self.assertIn("review", services.allowed_actions(self.alice, mission))
