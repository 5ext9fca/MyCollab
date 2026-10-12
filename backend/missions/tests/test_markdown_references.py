from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import ValidationFailure
from library.models import LibraryFile
from missions import services


def make_file(owner) -> LibraryFile:
    return LibraryFile.objects.create(
        owner=owner,
        file=f"library/{owner.id}/x",
        original_name="x.png",
        content_type="image/png",
        size=1,
    )


class MarkdownReferenceServiceTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.alice_file = make_file(self.alice)
        self.bob_file = make_file(self.bob)

    def test_create_mission_allows_own_file_and_external(self):
        mission = services.create_mission(
            actor=self.alice,
            title="t",
            content=(
                f"![a](/api/library/files/{self.alice_file.id}/) "
                "![b](https://cdn.example.com/b.png)"
            ),
        )
        self.assertIn(str(self.alice_file.id), mission.content)

    def test_create_mission_rejects_other_users_file(self):
        with self.assertRaises(ValidationFailure) as ctx:
            services.create_mission(
                actor=self.alice,
                title="t",
                content=f"![](/api/library/files/{self.bob_file.id}/)",
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("content", ctx.exception.field_errors)

    def test_create_mission_reports_acceptance_criteria_field(self):
        with self.assertRaises(ValidationFailure) as ctx:
            services.create_mission(actor=self.alice, title="t", acceptance_criteria="[x](/etc/passwd)")
        self.assertIn("acceptance_criteria", ctx.exception.field_errors)

    def test_update_mission_rejects_foreign_reference(self):
        mission = services.create_mission(actor=self.alice, title="t")
        with self.assertRaises(ValidationFailure):
            services.update_mission(
                actor=self.alice,
                mission_id=mission.id,
                version=mission.version,
                changes={"content": "[x](/tmp/a.png)"},
            )

    def test_submit_mission_validates_result(self):
        mission = services.create_mission(actor=self.alice, title="t")
        services.claim_mission(actor=self.bob, mission_id=mission.id)
        with self.assertRaises(ValidationFailure) as ctx:
            services.submit_mission(
                actor=self.bob,
                mission_id=mission.id,
                result=f"![](/api/library/files/{self.alice_file.id}/)",
            )
        self.assertIn("result", ctx.exception.field_errors)

    def test_comment_uses_the_authors_own_library(self):
        mission = services.create_mission(actor=self.alice, title="t")

        with self.assertRaises(ValidationFailure):
            services.create_comment(
                actor=self.alice,
                mission_id=mission.id,
                content=f"![](/api/library/files/{self.bob_file.id}/)",
            )

        comment = services.create_comment(
            actor=self.alice,
            mission_id=mission.id,
            content=f"![](/api/library/files/{self.alice_file.id}/)",
        )
        with self.assertRaises(ValidationFailure):
            services.update_comment(
                actor=self.alice, comment_id=comment.id, content="[x](/media/x.png)"
            )


class MarkdownReferenceApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.bob_file = make_file(self.bob)
        self.client = APIClient()

    def test_api_returns_400_with_field_errors(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post(
            "/api/missions/",
            {"title": "t", "content": f"![](/api/library/files/{self.bob_file.id}/)"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        self.assertIn("content", body["field_errors"])
