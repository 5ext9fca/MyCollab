from django.test import TestCase

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import MissionStatus


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
        self.assertEqual(
            set(mission.tags.values_list("name", flat=True)), {"Unity", "Gameplay"}
        )
        self.assertTrue(mission.events.filter(action="created").exists())

    def test_claim_sets_assignee_and_is_exclusive(self):
        mission = self._mission()
        mission = services.claim_mission(actor=self.bob, mission_id=mission.id)
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)
        self.assertEqual(mission.assignee_id, self.bob.id)
        self.assertEqual(mission.version, 2)
        with self.assertRaises(ConflictError):
            services.claim_mission(actor=self.carol, mission_id=mission.id)

    def test_release_returns_to_open(self):
        mission = self._mission()
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        mission = services.release_mission(actor=self.bob, mission_id=mission.id)
        self.assertEqual(mission.status, MissionStatus.OPEN)
        self.assertIsNone(mission.assignee_id)
        with self.assertRaises(PermissionDenied):
            services.release_mission(actor=self.carol, mission_id=mission.id)

    def test_submit_requires_assignee_result_and_complete_children(self):
        parent = self._mission()
        child = self._mission(parent_id=parent.id)
        services.claim_mission(actor=self.bob, mission_id=parent.id)

        with self.assertRaises(ValidationFailure):
            services.submit_mission(actor=self.bob, mission_id=parent.id, result="  ")
        with self.assertRaises(ConflictError):
            services.submit_mission(actor=self.bob, mission_id=parent.id, result="整合完成")
        with self.assertRaises(PermissionDenied):
            services.submit_mission(actor=self.carol, mission_id=parent.id, result="x")

        services.claim_mission(actor=self.carol, mission_id=child.id)
        services.submit_mission(actor=self.carol, mission_id=child.id, result="子任务完成")
        services.review_mission(actor=self.alice, mission_id=child.id, approve=True)

        parent = services.submit_mission(actor=self.bob, mission_id=parent.id, result="整合完成")
        self.assertEqual(parent.status, MissionStatus.SUBMITTED)

    def test_cancelled_child_does_not_block_parent(self):
        parent = self._mission()
        child = self._mission(parent_id=parent.id)
        services.claim_mission(actor=self.bob, mission_id=parent.id)
        services.cancel_mission(actor=self.alice, mission_id=child.id, reason="范围调整")
        parent = services.submit_mission(actor=self.bob, mission_id=parent.id, result="完成")
        self.assertEqual(parent.status, MissionStatus.SUBMITTED)

    def test_review_approve_and_reject(self):
        mission = self._mission()
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        services.submit_mission(actor=self.bob, mission_id=mission.id, result="成果")
        with self.assertRaises(PermissionDenied):
            services.review_mission(actor=self.bob, mission_id=mission.id, approve=True)

        mission = services.review_mission(
            actor=self.alice, mission_id=mission.id, approve=False, comment="再改改"
        )
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)

        services.submit_mission(actor=self.bob, mission_id=mission.id, result="成果v2")
        mission = services.review_mission(actor=self.alice, mission_id=mission.id, approve=True)
        self.assertEqual(mission.status, MissionStatus.DONE)

    def test_cancel_child_requires_reason(self):
        parent = self._mission()
        child = self._mission(parent_id=parent.id)
        with self.assertRaises(ValidationFailure):
            services.cancel_mission(actor=self.alice, mission_id=child.id, reason="")
        child = services.cancel_mission(actor=self.alice, mission_id=child.id, reason="不需要了")
        self.assertEqual(child.status, MissionStatus.CANCELLED)

    def test_cancel_keeps_assignee(self):
        mission = self._mission()
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        mission = services.cancel_mission(actor=self.alice, mission_id=mission.id)
        self.assertEqual(mission.status, MissionStatus.CANCELLED)
        self.assertEqual(mission.assignee_id, self.bob.id)

    def test_update_requires_creator_and_correct_version(self):
        mission = self._mission()
        with self.assertRaises(PermissionDenied):
            services.update_mission(
                actor=self.bob, mission_id=mission.id, version=mission.version, changes={"title": "x"}
            )
        mission = services.update_mission(
            actor=self.alice, mission_id=mission.id, version=mission.version, changes={"title": "v2"}
        )
        self.assertEqual(mission.title, "v2")
        with self.assertRaises(ConflictError):
            services.update_mission(
                actor=self.alice, mission_id=mission.id, version=1, changes={"title": "v3"}
            )

    def test_update_frozen_when_submitted(self):
        mission = self._mission()
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        mission = services.submit_mission(actor=self.bob, mission_id=mission.id, result="成果")
        with self.assertRaises(ConflictError):
            services.update_mission(
                actor=self.alice,
                mission_id=mission.id,
                version=mission.version,
                changes={"title": "改不了"},
            )

    def test_parent_rules(self):
        parent = self._mission()
        # Only the parent's creator or assignee may add children.
        with self.assertRaises(PermissionDenied):
            self._mission(actor=self.bob, parent_id=parent.id)

        child = self._mission(actor=self.alice, parent_id=parent.id)
        self.assertEqual(child.parent_id, parent.id)

        # A finished parent cannot receive new children.
        done_parent = self._mission(title="done")
        services.claim_mission(actor=self.bob, mission_id=done_parent.id)
        services.submit_mission(actor=self.bob, mission_id=done_parent.id, result="done")
        services.review_mission(actor=self.alice, mission_id=done_parent.id, approve=True)
        with self.assertRaises(ConflictError):
            self._mission(actor=self.alice, parent_id=done_parent.id)

    def test_parent_cycle_is_rejected(self):
        a = self._mission(title="a")
        b = self._mission(title="b", parent_id=a.id)
        with self.assertRaises(ConflictError):
            services.update_mission(
                actor=self.alice, mission_id=a.id, version=a.version, changes={"parent": b.id}
            )

    def test_allowed_actions(self):
        mission = self._mission()
        # Self-claim is allowed, so even the creator sees "claim".
        self.assertEqual(
            services.allowed_actions(self.alice, mission),
            ["claim", "edit", "cancel", "create_child"],
        )
        # A bystander can only claim.
        self.assertEqual(services.allowed_actions(self.bob, mission), ["claim"])

        mission = services.claim_mission(actor=self.bob, mission_id=mission.id)
        self.assertIn("submit", services.allowed_actions(self.bob, mission))
        mission = services.submit_mission(actor=self.bob, mission_id=mission.id, result="成果")
        self.assertIn("review", services.allowed_actions(self.alice, mission))
