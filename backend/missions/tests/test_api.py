from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services
from missions.models import MissionStatus


class AuthApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")

    def test_login_requires_csrf_then_authenticates(self):
        client = APIClient(enforce_csrf_checks=True)

        blocked = client.post(
            "/api/auth/login/", {"username": "alice", "password": "pw"}, format="json"
        )
        self.assertEqual(blocked.status_code, 403)

        token_response = client.get("/api/auth/csrf/")
        self.assertEqual(token_response.status_code, 200)
        token = client.cookies["csrftoken"].value

        ok = client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "pw"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(ok.status_code, 200)

        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "alice")

    def test_bad_credentials(self):
        client = APIClient()
        response = client.post(
            "/api/auth/login/", {"username": "alice", "password": "wrong"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "invalid_credentials")


class MissionApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")
        self.client = APIClient()

    def test_anonymous_is_rejected(self):
        # SessionAuthentication cannot issue a challenge, so DRF returns 403.
        response = self.client.get("/api/missions/")
        self.assertEqual(response.status_code, 403)

    def test_create_list_and_detail(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post(
            "/api/missions/",
            {
                "title": "实现移动系统",
                "content": "背景",
                "acceptance_criteria": "可跳跃",
                "tags": ["Unity", "Gameplay"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["status"], "Open")
        self.assertIsNone(data["assignee"])
        self.assertEqual({tag["name"] for tag in data["tags"]}, {"Unity", "Gameplay"})
        self.assertIn("claim", data["allowed_actions"])
        self.assertIn("children", data)

        listing = self.client.get("/api/missions/")
        self.assertEqual(listing.status_code, 200)
        body = listing.json()
        self.assertEqual(set(body.keys()), {"count", "next", "previous", "results"})
        self.assertEqual(body["count"], 1)

    def test_claim_conflict_returns_409_with_error_shape(self):
        mission = services.create_mission(actor=self.alice, title="t")
        self.client.force_authenticate(self.bob)
        first = self.client.post(f"/api/missions/{mission.id}/claim/", {}, format="json")
        self.assertEqual(first.status_code, 200)

        self.client.force_authenticate(self.carol)
        second = self.client.post(f"/api/missions/{mission.id}/claim/", {}, format="json")
        self.assertEqual(second.status_code, 409)
        body = second.json()
        self.assertEqual(body["code"], "claim_conflict")
        self.assertIn("message", body)
        self.assertIn("field_errors", body)

    def test_permission_denied_returns_403(self):
        mission = services.create_mission(actor=self.alice, title="t")
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        services.submit_mission(actor=self.bob, mission_id=mission.id, result="成果")
        self.client.force_authenticate(self.bob)
        response = self.client.post(
            f"/api/missions/{mission.id}/review/", {"approve": True}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_filters(self):
        services.create_mission(actor=self.alice, title="可认领", tags=["Unity"])
        claimed = services.create_mission(actor=self.alice, title="进行中")
        services.claim_mission(actor=self.bob, mission_id=claimed.id)

        self.client.force_authenticate(self.bob)

        open_only = self.client.get("/api/missions/?status=Open").json()
        self.assertEqual([m["title"] for m in open_only["results"]], ["可认领"])

        mine = self.client.get("/api/missions/?assignee=me").json()
        self.assertEqual([m["title"] for m in mine["results"]], ["进行中"])

        by_tag = self.client.get("/api/missions/?tag=Unity").json()
        self.assertEqual([m["title"] for m in by_tag["results"]], ["可认领"])

        search = self.client.get("/api/missions/?search=进行").json()
        self.assertEqual([m["title"] for m in search["results"]], ["进行中"])

        self.client.force_authenticate(self.alice)
        published = self.client.get("/api/missions/?creator=me").json()
        self.assertEqual(published["count"], 2)

    def test_multi_tag_filter_requires_all_tags(self):
        services.create_mission(actor=self.alice, title="两个标签", tags=["Unity", "Gameplay"])
        services.create_mission(actor=self.alice, title="只有 Unity", tags=["Unity"])
        services.create_mission(actor=self.alice, title="只有 Gameplay", tags=["Gameplay"])
        self.client.force_authenticate(self.alice)

        # Repeated params are ANDed: only the mission carrying both tags matches.
        both = self.client.get("/api/missions/?tag=Unity&tag=Gameplay").json()
        self.assertEqual([m["title"] for m in both["results"]], ["两个标签"])

        # The comma form is equivalent.
        comma = self.client.get("/api/missions/?tag=Unity,Gameplay").json()
        self.assertEqual([m["title"] for m in comma["results"]], ["两个标签"])

        # A single tag still matches every mission carrying it.
        single = self.client.get("/api/missions/?tag=Unity").json()
        self.assertEqual({m["title"] for m in single["results"]}, {"两个标签", "只有 Unity"})

        # One unknown tag makes the AND unsatisfiable.
        missing = self.client.get("/api/missions/?tag=Unity&tag=Missing").json()
        self.assertEqual(missing["count"], 0)

        # A blank value adds no filter.
        blank = self.client.get("/api/missions/?tag=").json()
        self.assertEqual(blank["count"], 3)

    def test_invalid_filter_is_400(self):
        self.client.force_authenticate(self.alice)
        response = self.client.get("/api/missions/?creator=not-a-uuid")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_tags_endpoint(self):
        services.create_mission(actor=self.alice, title="t", tags=["Unity"])
        self.client.force_authenticate(self.alice)
        response = self.client.get("/api/tags/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "Unity")

    def test_events_endpoint(self):
        mission = services.create_mission(actor=self.alice, title="t")
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        self.client.force_authenticate(self.alice)
        response = self.client.get(f"/api/missions/{mission.id}/events/")
        self.assertEqual(response.status_code, 200)
        actions = [event["action"] for event in response.json()["results"]]
        self.assertIn("claimed", actions)
        self.assertIn("created", actions)

    def test_cannot_put_or_delete(self):
        mission = services.create_mission(actor=self.alice, title="t")
        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.put(f"/api/missions/{mission.id}/", {"title": "x"}, format="json").status_code,
            405,
        )
        self.assertEqual(self.client.delete(f"/api/missions/{mission.id}/").status_code, 405)
