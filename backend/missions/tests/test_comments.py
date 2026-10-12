import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services

from . import utils


class CommentApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.client = APIClient()
        self.mission = services.create_mission(actor=self.alice, title="t")

    def url(self, mission=None) -> str:
        return f"/api/missions/{(mission or self.mission).id}/comments/"

    def test_anonymous_cannot_read_or_write_comments(self):
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(
            self.client.post(self.url(), {"content": "hi"}, format="json").status_code, 403
        )
        self.assertEqual(
            self.client.patch(f"/api/comments/{uuid.uuid4()}/", {"content": "x"}, format="json").status_code,
            403,
        )

    def test_member_creates_and_lists_comments(self):
        self.client.force_authenticate(self.bob)

        created = self.client.post(self.url(), {"content": "**看起来不错**"}, format="json")

        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertEqual(body["content"], "**看起来不错**")
        self.assertEqual(body["author"]["username"], "bob")
        self.assertEqual(str(body["mission"]), str(self.mission.id))
        self.assertTrue(body["can_edit"])

        listing = self.client.get(self.url())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(set(listing.json().keys()), {"count", "next", "previous", "results"})
        self.assertEqual(listing.json()["count"], 1)

    def test_can_edit_flag_is_false_for_non_authors(self):
        self.client.force_authenticate(self.bob)
        self.client.post(self.url(), {"content": "hi"}, format="json")

        self.client.force_authenticate(self.alice)
        row = self.client.get(self.url()).json()["results"][0]
        self.assertFalse(row["can_edit"])

    def test_comments_allowed_in_done_and_cancelled_status(self):
        utils.claim(self.bob, self.mission)
        utils.submit(self.bob, self.mission)
        utils.review(self.alice, self.mission, decision="accept")

        cancelled = services.create_mission(actor=self.alice, title="c")
        utils.cancel(self.alice, cancelled)

        self.client.force_authenticate(self.bob)
        self.assertEqual(
            self.client.post(self.url(), {"content": "done!"}, format="json").status_code, 201
        )
        self.assertEqual(
            self.client.post(self.url(cancelled), {"content": "c"}, format="json").status_code,
            201,
        )

    def test_author_edits_own_comment(self):
        self.client.force_authenticate(self.bob)
        comment_id = self.client.post(self.url(), {"content": "旧"}, format="json").json()["id"]

        response = self.client.patch(
            f"/api/comments/{comment_id}/", {"content": "新"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "新")

    def test_non_author_cannot_edit_or_delete(self):
        self.client.force_authenticate(self.bob)
        comment_id = self.client.post(self.url(), {"content": "x"}, format="json").json()["id"]

        self.client.force_authenticate(self.alice)
        blocked_edit = self.client.patch(
            f"/api/comments/{comment_id}/", {"content": "y"}, format="json"
        )
        self.assertEqual(blocked_edit.status_code, 403)
        self.assertEqual(blocked_edit.json()["code"], "permission_denied")
        self.assertEqual(self.client.delete(f"/api/comments/{comment_id}/").status_code, 403)

    def test_author_deletes_own_comment(self):
        self.client.force_authenticate(self.bob)
        comment_id = self.client.post(self.url(), {"content": "x"}, format="json").json()["id"]

        self.assertEqual(self.client.delete(f"/api/comments/{comment_id}/").status_code, 204)
        self.assertEqual(self.client.get(self.url()).json()["count"], 0)

    def test_content_mirrors_mission_content(self):
        # Same field definition as Mission.content: blank allowed, Markdown stored verbatim.
        self.client.force_authenticate(self.bob)

        blank = self.client.post(self.url(), {}, format="json")
        self.assertEqual(blank.status_code, 201)
        self.assertEqual(blank.json()["content"], "")

        markdown = "# 标题\n\n- 项一\n- 项二"
        stored = self.client.post(self.url(), {"content": markdown}, format="json")
        self.assertEqual(stored.json()["content"], markdown)

    def test_update_requires_content(self):
        self.client.force_authenticate(self.bob)
        comment_id = self.client.post(self.url(), {"content": "x"}, format="json").json()["id"]

        response = self.client.patch(f"/api/comments/{comment_id}/", {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_missing_mission_or_comment_is_404(self):
        self.client.force_authenticate(self.bob)
        missing = uuid.uuid4()

        self.assertEqual(self.client.get(f"/api/missions/{missing}/comments/").status_code, 404)
        self.assertEqual(
            self.client.post(f"/api/missions/{missing}/comments/", {"content": "x"}, format="json").status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(f"/api/comments/{missing}/", {"content": "x"}, format="json").status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"/api/comments/{missing}/").status_code, 404)
