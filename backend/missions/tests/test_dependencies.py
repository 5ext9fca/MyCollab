from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import MissionDependency, MissionStatus

from . import utils


class DependencyServiceTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")

    def _mission(self, **kwargs):
        defaults = {"actor": self.alice, "title": "t"}
        defaults.update(kwargs)
        return services.create_mission(**defaults)

    def _add(self, mission, prerequisite, actor=None, version=None):
        return services.add_dependency(
            actor=actor or self.alice,
            mission_id=mission.id,
            prerequisite_id=prerequisite.id,
            expected_version=version if version is not None else utils.version_of(mission),
        )

    def test_add_and_remove_dependency_increments_version(self):
        prereq = self._mission(title="前置")
        dependent = self._mission(title="依赖")
        before = dependent.version
        dependency = self._add(dependent, prereq)
        dependent = utils.fresh(dependent)
        self.assertEqual(dependent.version, before + 1)
        self.assertTrue(
            MissionDependency.objects.filter(mission=dependent, prerequisite=prereq).exists()
        )
        self.assertTrue(
            dependent.events.filter(action="dependency_added").exists()
        )

        services.remove_dependency(
            actor=self.alice,
            mission_id=dependent.id,
            dependency_id=dependency.id,
            expected_version=utils.version_of(dependent),
        )
        self.assertFalse(MissionDependency.objects.filter(pk=dependency.id).exists())
        self.assertTrue(utils.fresh(dependent).events.filter(action="dependency_removed").exists())

    def test_self_and_duplicate_dependency_rejected(self):
        mission = self._mission()
        with self.assertRaises(ValidationFailure):
            self._add(mission, mission)
        prereq = self._mission(title="p")
        self._add(mission, prereq)
        with self.assertRaises(ConflictError) as ctx:
            self._add(mission, prereq)
        self.assertEqual(ctx.exception.code, "dependency_exists")

    def test_explicit_cycle_rejected(self):
        a = self._mission(title="a")
        b = self._mission(title="b")
        self._add(a, b)  # a depends on b => b -> a
        with self.assertRaises(ConflictError) as ctx:
            self._add(b, a)  # b depends on a => a -> b closes the cycle
        self.assertEqual(ctx.exception.code, "dependency_cycle")

    def test_transitive_cycle_rejected(self):
        a = self._mission(title="a")
        b = self._mission(title="b")
        c = self._mission(title="c")
        self._add(a, b)
        self._add(b, c)
        with self.assertRaises(ConflictError):
            self._add(c, a)

    def test_child_cannot_depend_on_ancestor(self):
        # parent -> child implicit completion edge means child must finish first.
        parent = self._mission(title="parent")
        child = self._mission(title="child", parent_id=parent.id)
        with self.assertRaises(ConflictError) as ctx:
            self._add(child, parent)
        self.assertEqual(ctx.exception.code, "dependency_cycle")

    def test_reparenting_that_forms_cycle_is_rejected(self):
        a = self._mission(title="a")
        c = self._mission(title="c")
        # a depends on c => completion edge c -> a. Making c the parent of a adds
        # edge a -> c, which closes a cycle combining parent + dependency edges.
        self._add(a, c)
        with self.assertRaises(ConflictError):
            services.update_mission(
                actor=self.alice,
                mission_id=a.id,
                expected_version=utils.version_of(a),
                changes={"parent": c.id},
            )

    def test_cross_parent_dependency_allowed(self):
        p1 = self._mission(title="p1")
        child1 = self._mission(title="c1", parent_id=p1.id)
        p2 = self._mission(title="p2")
        child2 = self._mission(title="c2", parent_id=p2.id)
        # c2 depends on c1 across different parents: allowed.
        self._add(child2, child1)
        self.assertTrue(
            MissionDependency.objects.filter(mission=child2, prerequisite=child1).exists()
        )

    def test_only_creator_assignee_or_admin_can_edit_dependencies(self):
        mission = self._mission()
        prereq = self._mission(title="p")
        with self.assertRaises(PermissionDenied):
            self._add(mission, prereq, actor=self.bob)
        # The current assignee may manage dependencies.
        utils.claim(self.bob, mission)
        self._add(mission, prereq, actor=self.bob)
        # Admin too.
        admin = User.objects.create_user("admin", password="pw", is_staff=True)
        other = self._mission(title="o")
        self._add(other, prereq, actor=admin)

    def test_dependencies_frozen_after_submit(self):
        prereq = self._mission(title="p")
        mission = self._mission(title="m")
        utils.claim(self.bob, mission)
        mission = utils.submit(self.bob, mission)
        with self.assertRaises(ConflictError):
            self._add(mission, prereq)

    def test_cancelled_prerequisite_still_blocks(self):
        prereq = self._mission(title="p")
        mission = self._mission(title="m")
        self._add(mission, prereq)
        utils.cancel(self.alice, prereq, reason="范围调整")
        state = services.derived_state(utils.fresh(mission))
        self.assertTrue(state["has_unresolved_prerequisites"])
        self.assertTrue(state["is_blocked"])

    def test_blocked_mission_can_be_claimed_but_not_submitted(self):
        prereq = self._mission(title="p")
        mission = self._mission(title="m")
        self._add(mission, prereq)

        mission = utils.claim(self.bob, mission)
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)
        with self.assertRaises(ConflictError) as ctx:
            utils.submit(self.bob, mission)
        self.assertEqual(ctx.exception.code, "prerequisites_incomplete")

    def test_done_prerequisite_unblocks_submission(self):
        prereq = self._mission(title="p")
        mission = self._mission(title="m")
        self._add(mission, prereq)
        utils.claim(self.bob, prereq)
        utils.submit(self.bob, prereq)
        utils.review(self.alice, prereq, decision="accept")

        utils.claim(self.carol, mission)
        mission = utils.submit(self.carol, mission)
        self.assertEqual(mission.status, MissionStatus.SUBMITTED)

    def test_reopened_prerequisite_blocks_review_and_flags_review_needed(self):
        prereq = self._mission(title="p")
        mission = self._mission(title="m")
        self._add(mission, prereq)
        utils.claim(self.bob, prereq)
        utils.submit(self.bob, prereq)
        utils.review(self.alice, prereq, decision="accept")

        utils.claim(self.carol, mission)
        mission = utils.submit(self.carol, mission)

        # Reopen the prerequisite while the downstream is Submitted.
        prereq = utils.fresh(prereq)
        services.reopen_mission(
            actor=self.alice,
            mission_id=prereq.id,
            reason="发现缺陷",
            expected_version=utils.version_of(prereq),
        )
        mission = utils.fresh(mission)
        state = services.derived_state(mission)
        self.assertTrue(state["is_blocked"])
        with self.assertRaises(ConflictError):
            utils.review(self.alice, mission, decision="accept")

    def test_done_downstream_flags_needs_dependency_review(self):
        prereq = self._mission(title="p")
        mission = self._mission(title="m")
        self._add(mission, prereq)
        utils.claim(self.bob, prereq)
        utils.submit(self.bob, prereq)
        utils.review(self.alice, prereq, decision="accept")

        utils.claim(self.carol, mission)
        utils.submit(self.carol, mission)
        utils.review(self.alice, mission, decision="accept")
        self.assertEqual(utils.fresh(mission).status, MissionStatus.DONE)

        prereq = utils.fresh(prereq)
        services.reopen_mission(
            actor=self.alice,
            mission_id=prereq.id,
            reason="回归",
            expected_version=utils.version_of(prereq),
        )
        mission = utils.fresh(mission)
        self.assertEqual(mission.status, MissionStatus.DONE)  # not auto-reopened
        state = services.derived_state(mission)
        self.assertTrue(state["needs_dependency_review"])
        self.assertTrue(state["has_unresolved_prerequisites"])


class DependencyApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.client = APIClient()
        self.mission = services.create_mission(actor=self.alice, title="m")
        self.prereq = services.create_mission(actor=self.alice, title="p")

    def test_add_list_and_delete_dependency(self):
        self.client.force_authenticate(self.alice)
        created = self.client.post(
            f"/api/missions/{self.mission.id}/dependencies/",
            {"prerequisite_id": str(self.prereq.id), "expected_version": self.mission.version},
            format="json",
        )
        self.assertEqual(created.status_code, 200, created.content)

        listing = self.client.get(f"/api/missions/{self.mission.id}/dependencies/")
        self.assertEqual(listing.status_code, 200)
        body = listing.json()
        self.assertEqual([p["id"] for p in body["prerequisites"]], [str(self.prereq.id)])
        self.assertTrue(body["has_unresolved_prerequisites"])

        dependency_id = MissionDependency.objects.get(
            mission=self.mission, prerequisite=self.prereq
        ).id
        self.assertEqual(str(body["prerequisites"][0]["dependency_id"]), str(dependency_id))
        version = utils.version_of(self.mission)
        deleted = self.client.delete(
            f"/api/missions/{self.mission.id}/dependencies/{dependency_id}/?expected_version={version}"
        )
        self.assertEqual(deleted.status_code, 204)

    def test_dependency_detail_and_filters(self):
        services.add_dependency(
            actor=self.alice,
            mission_id=self.mission.id,
            prerequisite_id=self.prereq.id,
            expected_version=self.mission.version,
        )
        self.client.force_authenticate(self.alice)

        detail = self.client.get(f"/api/missions/{self.mission.id}/").json()
        self.assertEqual([p["id"] for p in detail["prerequisites"]], [str(self.prereq.id)])
        edge = MissionDependency.objects.get(mission=self.mission, prerequisite=self.prereq)
        self.assertEqual([p["dependency_id"] for p in detail["prerequisites"]], [str(edge.id)])
        self.assertTrue(detail["is_blocked"])

        prereq_detail = self.client.get(f"/api/missions/{self.prereq.id}/").json()
        self.assertEqual([d["id"] for d in prereq_detail["dependents"]], [str(self.mission.id)])

        blocked = self.client.get("/api/missions/?blocked=true").json()
        self.assertEqual([m["title"] for m in blocked["results"]], ["m"])
