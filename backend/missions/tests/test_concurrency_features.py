"""Concurrency scenarios from NEW_FUNCTION.md section 9 (PostgreSQL only).

These use ``TransactionTestCase`` (real commits) and one connection per thread so
the Postgres advisory lock / row locks actually serialize.
"""

import threading

from django.db import connections
from django.test import TransactionTestCase

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError
from missions.models import Milestone, MilestoneStatus, Mission, MissionDependency, MissionStatus


def run_concurrently(fn_a, fn_b):
    barrier = threading.Barrier(2)
    results: dict = {}
    lock = threading.Lock()

    def wrap(name, fn):
        barrier.wait()
        try:
            fn()
            outcome = "ok"
        except Exception as exc:  # noqa: BLE001 - recorded for assertions
            outcome = exc
        finally:
            connections.close_all()
        with lock:
            results[name] = outcome

    threads = [
        threading.Thread(target=wrap, args=("a", fn_a)),
        threading.Thread(target=wrap, args=("b", fn_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


class DependencyConcurrencyTests(TransactionTestCase):
    def test_concurrent_opposite_dependencies_keep_graph_acyclic(self):
        alice = User.objects.create_user("alice", password="pw")
        a = services.create_mission(actor=alice, title="a")
        b = services.create_mission(actor=alice, title="b")

        results = run_concurrently(
            lambda: services.add_dependency(
                actor=alice,
                mission_id=a.id,
                prerequisite_id=b.id,
                expected_version=Mission.objects.values_list("version", flat=True).get(pk=a.id),
            ),
            lambda: services.add_dependency(
                actor=alice,
                mission_id=b.id,
                prerequisite_id=a.id,
                expected_version=Mission.objects.values_list("version", flat=True).get(pk=b.id),
            ),
        )

        outcomes = list(results.values())
        self.assertEqual(outcomes.count("ok"), 1, results)
        self.assertEqual(MissionDependency.objects.count(), 1)


class ReviewConcurrencyTests(TransactionTestCase):
    def test_duplicate_review_only_succeeds_once(self):
        alice = User.objects.create_user("alice", password="pw")
        bob = User.objects.create_user("bob", password="pw")
        mission = services.create_mission(actor=alice, title="t")
        services.claim_mission(
            actor=bob, mission_id=mission.id, expected_version=mission.version
        )
        mission = services.submit_mission(
            actor=bob,
            mission_id=mission.id,
            description="成果",
            verification_description="人工验证",
            expected_version=Mission.objects.values_list("version", flat=True).get(pk=mission.id),
        )
        submission_id = mission.current_submission_id

        def review():
            version = Mission.objects.values_list("version", flat=True).get(pk=mission.id)
            services.review_mission(
                actor=alice,
                mission_id=mission.id,
                submission_id=submission_id,
                decision="accept",
                comment="人工验证通过",
                expected_version=version,
            )

        results = run_concurrently(review, review)
        self.assertEqual(list(results.values()).count("ok"), 1, results)
        refreshed = Mission.objects.get(pk=mission.id)
        self.assertEqual(refreshed.status, MissionStatus.DONE)


class ReopenReviewConcurrencyTests(TransactionTestCase):
    def test_reopened_prerequisite_never_gets_accepted_downstream(self):
        alice = User.objects.create_user("alice", password="pw")
        bob = User.objects.create_user("bob", password="pw")
        carol = User.objects.create_user("carol", password="pw")

        prereq = services.create_mission(actor=alice, title="p")
        services.claim_mission(actor=bob, mission_id=prereq.id, expected_version=prereq.version)
        prereq = services.submit_mission(
            actor=bob,
            mission_id=prereq.id,
            description="p",
            verification_description="人工验证",
            expected_version=Mission.objects.values_list("version", flat=True).get(pk=prereq.id),
        )
        services.review_mission(
            actor=alice,
            mission_id=prereq.id,
            submission_id=prereq.current_submission_id,
            decision="accept",
            comment="人工验证通过",
            expected_version=Mission.objects.values_list("version", flat=True).get(pk=prereq.id),
        )

        mission = services.create_mission(actor=alice, title="m")
        services.add_dependency(
            actor=alice,
            mission_id=mission.id,
            prerequisite_id=prereq.id,
            expected_version=Mission.objects.values_list("version", flat=True).get(pk=mission.id),
        )
        services.claim_mission(
            actor=carol,
            mission_id=mission.id,
            expected_version=Mission.objects.values_list("version", flat=True).get(pk=mission.id),
        )
        mission = services.submit_mission(
            actor=carol,
            mission_id=mission.id,
            description="m",
            verification_description="人工验证",
            expected_version=Mission.objects.values_list("version", flat=True).get(pk=mission.id),
        )
        submission_id = mission.current_submission_id

        def reopen():
            version = Mission.objects.values_list("version", flat=True).get(pk=prereq.id)
            services.reopen_mission(
                actor=alice, mission_id=prereq.id, reason="回归", expected_version=version
            )

        def review():
            version = Mission.objects.values_list("version", flat=True).get(pk=mission.id)
            services.review_mission(
                actor=alice,
                mission_id=mission.id,
                submission_id=submission_id,
                decision="accept",
                comment="人工验证通过",
                expected_version=version,
            )

        run_concurrently(reopen, review)

        prereq.refresh_from_db()
        mission.refresh_from_db()
        self.assertEqual(prereq.status, MissionStatus.IN_PROGRESS)
        state = services.derived_state(mission)
        if mission.status == MissionStatus.DONE:
            self.assertTrue(state["needs_dependency_review"], state)
        else:
            self.assertEqual(mission.status, MissionStatus.SUBMITTED)
            self.assertTrue(state["is_blocked"], state)


class MilestoneConcurrencyTests(TransactionTestCase):
    def test_milestone_completion_and_new_task_are_mutually_exclusive(self):
        alice = User.objects.create_user("alice", password="pw")
        bob = User.objects.create_user("bob", password="pw")
        milestone = services.create_milestone(actor=alice, name="m")
        milestone = services.transition_milestone(
            actor=alice,
            milestone_id=milestone.id,
            status=MilestoneStatus.ACTIVE,
            expected_version=milestone.version,
        )
        done_mission = services.create_mission(actor=alice, title="done", milestone_id=milestone.id)
        services.claim_mission(
            actor=bob, mission_id=done_mission.id, expected_version=done_mission.version
        )
        done_mission = services.submit_mission(
            actor=bob,
            mission_id=done_mission.id,
            description="done",
            verification_description="人工验证",
            expected_version=Mission.objects.values_list("version", flat=True).get(
                pk=done_mission.id
            ),
        )
        services.review_mission(
            actor=alice,
            mission_id=done_mission.id,
            submission_id=done_mission.current_submission_id,
            decision="accept",
            comment="人工验证通过",
            expected_version=Mission.objects.values_list("version", flat=True).get(
                pk=done_mission.id
            ),
        )

        def complete():
            version = Milestone.objects.values_list("version", flat=True).get(pk=milestone.id)
            services.transition_milestone(
                actor=alice,
                milestone_id=milestone.id,
                status=MilestoneStatus.COMPLETED,
                expected_version=version,
            )

        def add_task():
            services.create_mission(actor=alice, title="new", milestone_id=milestone.id)

        run_concurrently(complete, add_task)

        milestone = Milestone.objects.get(pk=milestone.id)
        if milestone.status == MilestoneStatus.COMPLETED:
            # A closed milestone must not contain new unfinished work.
            self.assertFalse(
                milestone.missions.exclude(
                    status__in=[MissionStatus.DONE, MissionStatus.CANCELLED]
                ).exists()
            )
        else:
            self.assertEqual(milestone.status, MilestoneStatus.ACTIVE)
