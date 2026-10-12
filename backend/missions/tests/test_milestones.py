import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import Milestone, MilestoneStatus, MissionPriority, MissionStatus, MissionType

from . import utils


class PriorityServiceTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")

    def _mission(self, **kwargs):
        defaults = {"actor": self.alice, "title": "t"}
        defaults.update(kwargs)
        return services.create_mission(**defaults)

    def test_default_priority_is_p2(self):
        self.assertEqual(self._mission().priority, MissionPriority.P2)

    def test_creator_changes_priority_and_records_event(self):
        mission = self._mission()
        mission = utils.update(self.alice, mission, changes={"priority": "P0"})
        self.assertEqual(mission.priority, MissionPriority.P0)
        self.assertTrue(mission.events.filter(action="priority_changed").exists())

    def test_assignee_cannot_change_priority(self):
        mission = self._mission()
        utils.claim(self.bob, mission)
        with self.assertRaises(PermissionDenied):
            utils.update(self.bob, mission, changes={"priority": "P0"})

    def test_invalid_priority_rejected(self):
        mission = self._mission()
        with self.assertRaises(ValidationFailure):
            utils.update(self.alice, mission, changes={"priority": "P9"})

    def test_priority_ordering_is_stable(self):
        p2 = self._mission(title="p2", priority="P2")
        p0 = self._mission(title="p0", priority="P0")
        p1 = self._mission(title="p1", priority="P1")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        ordered = self.client.get("/api/missions/?ordering=priority").json()
        self.assertEqual([m["title"] for m in ordered["results"]], ["p0", "p1", "p2"])

    def test_type_and_priority_filters(self):
        self._mission(title="feature", type="Feature", priority="P1")
        self._mission(title="bug", type="Bug", priority="P0")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        self.assertEqual(
            [m["title"] for m in self.client.get("/api/missions/?type=Feature").json()["results"]],
            ["feature"],
        )
        self.assertEqual(
            [m["title"] for m in self.client.get("/api/missions/?priority=P0").json()["results"]],
            ["bug"],
        )
        self.assertEqual(self.client.get("/api/missions/?type=Nope").status_code, 400)


class MilestoneServiceTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.admin = User.objects.create_user("admin", password="pw", is_staff=True)

    def _milestone(self, **kwargs):
        defaults = {"actor": self.alice, "name": "首个可玩版本"}
        defaults.update(kwargs)
        return services.create_milestone(**defaults)

    def _complete_mission(self, actor, mission):
        utils.claim(actor, mission)
        utils.submit(actor, mission)
        return utils.review(self.alice, mission, decision="accept")

    def test_create_defaults_and_member_can_create(self):
        milestone = self._milestone()
        self.assertEqual(milestone.status, MilestoneStatus.PLANNED)
        self.assertEqual(milestone.version, 1)
        self.assertEqual(milestone.created_by_id, self.alice.id)
        self.assertTrue(milestone.events.filter(action="created").exists())
        # Any team member may create.
        self._milestone(actor=self.bob, name="bob 的里程碑")

    def test_update_only_by_creator_or_admin(self):
        milestone = self._milestone()
        with self.assertRaises(PermissionDenied):
            services.update_milestone(
                actor=self.bob,
                milestone_id=milestone.id,
                expected_version=milestone.version,
                changes={"name": "x"},
            )
        milestone = services.update_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            expected_version=milestone.version,
            changes={"name": "改", "due_date": datetime.date(2026, 12, 1)},
        )
        self.assertEqual(milestone.version, 2)
        self.assertEqual(milestone.due_date, datetime.date(2026, 12, 1))
        services.update_milestone(
            actor=self.admin,
            milestone_id=milestone.id,
            expected_version=milestone.version,
            changes={"name": "管理员改"},
        )

    def test_controlled_transitions(self):
        milestone = self._milestone()
        milestone = services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.ACTIVE,
            expected_version=milestone.version,
        )
        self.assertEqual(milestone.status, MilestoneStatus.ACTIVE)
        # Active -> Completed needs at least one effective task; none yet.
        with self.assertRaises(ConflictError) as ctx:
            services.transition_milestone(
                actor=self.alice,
                milestone_id=milestone.id,
                status=MilestoneStatus.COMPLETED,
                expected_version=milestone.version,
            )
        self.assertEqual(ctx.exception.code, "milestone_no_effective_tasks")
        # Planned -> Completed directly is not allowed.
        planned = self._milestone(name="p")
        with self.assertRaises(ConflictError) as ctx2:
            services.transition_milestone(
                actor=self.alice,
                milestone_id=planned.id,
                status=MilestoneStatus.COMPLETED,
                expected_version=planned.version,
            )
        self.assertEqual(ctx2.exception.code, "milestone_transition_invalid")

    def test_completion_requires_all_effective_tasks_done(self):
        milestone = self._milestone()
        services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.ACTIVE,
            expected_version=milestone.version,
        )
        m1 = services.create_mission(actor=self.alice, title="m1", milestone_id=milestone.id)
        m2 = services.create_mission(actor=self.alice, title="m2", milestone_id=milestone.id)
        self._complete_mission(self.bob, m1)

        milestone = Milestone.objects.get(pk=milestone.id)
        with self.assertRaises(ConflictError) as ctx:
            services.transition_milestone(
                actor=self.alice,
                milestone_id=milestone.id,
                status=MilestoneStatus.COMPLETED,
                expected_version=milestone.version,
            )
        self.assertEqual(ctx.exception.code, "milestone_tasks_incomplete")

        self._complete_mission(self.bob, m2)
        milestone = Milestone.objects.get(pk=milestone.id)
        milestone = services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.COMPLETED,
            expected_version=milestone.version,
        )
        self.assertEqual(milestone.status, MilestoneStatus.COMPLETED)

    def test_cancelled_only_milestone_cannot_complete(self):
        milestone = self._milestone()
        services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.ACTIVE,
            expected_version=milestone.version,
        )
        m = services.create_mission(actor=self.alice, title="m", milestone_id=milestone.id)
        utils.cancel(self.alice, m, reason="取消")
        milestone = Milestone.objects.get(pk=milestone.id)
        with self.assertRaises(ConflictError) as ctx:
            services.transition_milestone(
                actor=self.alice,
                milestone_id=milestone.id,
                status=MilestoneStatus.COMPLETED,
                expected_version=milestone.version,
            )
        self.assertEqual(ctx.exception.code, "milestone_no_effective_tasks")

    def test_restore_requires_reason(self):
        milestone = self._milestone()
        milestone = services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.CANCELLED,
            expected_version=milestone.version,
        )
        with self.assertRaises(ValidationFailure):
            services.transition_milestone(
                actor=self.alice,
                milestone_id=milestone.id,
                status=MilestoneStatus.ACTIVE,
                expected_version=milestone.version,
            )
        milestone = services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.ACTIVE,
            reason="重新启用",
            expected_version=milestone.version,
        )
        self.assertEqual(milestone.status, MilestoneStatus.ACTIVE)

    def test_only_planned_or_active_accept_missions(self):
        milestone = self._milestone()
        services.transition_milestone(
            actor=self.alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.CANCELLED,
            expected_version=milestone.version,
        )
        with self.assertRaises(ConflictError) as ctx:
            services.create_mission(actor=self.alice, title="x", milestone_id=milestone.id)
        self.assertEqual(ctx.exception.code, "milestone_not_accepting")

    def test_progress_and_overdue(self):
        milestone = self._milestone(due_date=datetime.date(2000, 1, 1))
        m1 = services.create_mission(actor=self.alice, title="m1", milestone_id=milestone.id)
        m2 = services.create_mission(actor=self.alice, title="m2", milestone_id=milestone.id)
        self._complete_mission(self.bob, m1)

        progress = services.milestone_progress(milestone)
        self.assertEqual(progress["effective_total"], 2)
        self.assertEqual(progress["done"], 1)
        self.assertEqual(progress["progress"], 0.5)

        empty = self._milestone(name="empty")
        self.assertIsNone(services.milestone_progress(empty)["progress"])

        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        detail = self.client.get(f"/api/milestones/{milestone.id}/").json()
        self.assertEqual(detail["progress"], 0.5)
        self.assertTrue(detail["overdue"])

    def test_milestone_filter_on_missions(self):
        milestone = self._milestone()
        inside = services.create_mission(actor=self.alice, title="in", milestone_id=milestone.id)
        services.create_mission(actor=self.alice, title="out")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        filtered = self.client.get(f"/api/missions/?milestone={milestone.id}").json()
        self.assertEqual([m["id"] for m in filtered["results"]], [str(inside.id)])
        none = self.client.get("/api/missions/?milestone=none").json()
        self.assertEqual([m["title"] for m in none["results"]], ["out"])


class MilestoneApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.client = APIClient()

    def test_create_list_update_and_transition(self):
        self.client.force_authenticate(self.alice)
        created = self.client.post(
            "/api/milestones/",
            {"name": "首个可玩版本", "description": "目标", "due_date": "2026-12-01"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertEqual(body["status"], "Planned")
        milestone_id = body["id"]

        listing = self.client.get("/api/milestones/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)

        patched = self.client.patch(
            f"/api/milestones/{milestone_id}/",
            {"name": "改名", "expected_version": body["version"]},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.content)

        transitioned = self.client.post(
            f"/api/milestones/{milestone_id}/transition/",
            {"status": "Active", "expected_version": patched.json()["version"]},
            format="json",
        )
        self.assertEqual(transitioned.status_code, 200, transitioned.content)
        self.assertEqual(transitioned.json()["status"], "Active")

    def test_transition_requires_version(self):
        self.client.force_authenticate(self.alice)
        milestone = services.create_milestone(actor=self.alice, name="m")
        response = self.client.post(
            f"/api/milestones/{milestone.id}/transition/",
            {"status": "Active"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
