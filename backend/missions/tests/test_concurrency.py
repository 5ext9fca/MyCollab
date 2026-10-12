import threading

from django.db import connections
from django.test import TransactionTestCase

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError
from missions.models import Mission, MissionEvent, MissionStatus


class ClaimConcurrencyTests(TransactionTestCase):
    """Concurrent claims must resolve to exactly one winner.

    Uses ``TransactionTestCase`` (real commits) and independent per-thread
    connections, so it only makes sense on PostgreSQL. SQLite would serialize
    the writes and hide the race.
    """

    def test_only_one_concurrent_claim_succeeds(self):
        creator = User.objects.create_user("creator", password="pw")
        mission = services.create_mission(actor=creator, title="并发认领")
        users = [User.objects.create_user(f"user{i}", password="pw") for i in range(4)]

        barrier = threading.Barrier(len(users))
        results = []
        lock = threading.Lock()

        def worker(user):
            barrier.wait()
            try:
                version = Mission.objects.values_list("version", flat=True).get(pk=mission.id)
                services.claim_mission(
                    actor=user, mission_id=mission.id, expected_version=version
                )
                outcome = "ok"
            except ConflictError:
                outcome = "conflict"
            except Exception as exc:  # pragma: no cover - surfaced in assertion
                outcome = f"error:{exc!r}"
            finally:
                connections.close_all()
            with lock:
                results.append((user.username, outcome))

        threads = [threading.Thread(target=worker, args=(user,)) for user in users]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        outcomes = [outcome for _, outcome in results]
        self.assertEqual(outcomes.count("ok"), 1, results)
        self.assertEqual(outcomes.count("conflict"), len(users) - 1, results)

        mission.refresh_from_db()
        self.assertEqual(mission.status, MissionStatus.IN_PROGRESS)
        self.assertIsNotNone(mission.assignee_id)
        self.assertEqual(
            MissionEvent.objects.filter(mission=mission, action="claimed").count(), 1
        )
