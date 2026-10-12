import uuid

from django.test import TestCase

from accounts.models import User
from library.models import LibraryFile
from library.references import find_forbidden_references


class ReferenceRuleTests(TestCase):
    """Unit tests for the "only my own library or an external URL" rule."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")

    def make_file(self, owner) -> LibraryFile:
        return LibraryFile.objects.create(
            owner=owner,
            file=f"library/{owner.id}/x",
            original_name="x.png",
            content_type="image/png",
            size=1,
        )

    def test_own_library_file_is_allowed(self):
        record = self.make_file(self.alice)
        reference = f"/api/library/files/{record.id}/"

        self.assertEqual(find_forbidden_references(f"![alt]({reference})", self.alice), [])
        self.assertEqual(find_forbidden_references(f"[x]({reference})", self.alice), [])
        # A query string on the owner's own file is still allowed.
        self.assertEqual(
            find_forbidden_references(f"![a]({reference}?v=2)", self.alice), []
        )

    def test_other_users_library_file_is_forbidden(self):
        record = self.make_file(self.bob)
        reference = f"/api/library/files/{record.id}/"

        self.assertEqual(
            find_forbidden_references(f"![alt]({reference})", self.alice), [reference]
        )

    def test_unknown_library_id_is_forbidden(self):
        reference = f"/api/library/files/{uuid.uuid4()}/"
        self.assertEqual(
            find_forbidden_references(f"![alt]({reference})", self.alice), [reference]
        )

    def test_external_urls_are_allowed(self):
        markdown = (
            "![a](https://cdn.example.com/a.png) "
            "[b](http://example.com/b) "
            "![c](//cdn.example.com/c.png)"
        )
        self.assertEqual(find_forbidden_references(markdown, self.alice), [])

    def test_internal_and_unknown_schemes_are_forbidden(self):
        markdown = "\n".join(
            [
                "![a](/media/library/x/a.png)",
                "[b](/api/missions/123/)",
                "[c](../relative.png)",
                "[d](javascript:alert(1))",
                "![e](data:image/png;base64,AAAA)",
                "[f](mailto:a@example.com)",
            ]
        )
        self.assertEqual(
            set(find_forbidden_references(markdown, self.alice)),
            {
                "/media/library/x/a.png",
                "/api/missions/123/",
                "../relative.png",
                "javascript:alert(1)",
                "data:image/png;base64,AAAA",
                "mailto:a@example.com",
            },
        )

    def test_in_document_anchor_is_allowed(self):
        self.assertEqual(find_forbidden_references("[x](#section)", self.alice), [])

    def test_reference_definitions_are_checked(self):
        self.assertEqual(
            find_forbidden_references("[label]: /media/private/x.png", self.alice),
            ["/media/private/x.png"],
        )

    def test_raw_html_attributes_are_checked(self):
        other = self.make_file(self.bob)
        markdown = f'<img src="/api/library/files/{other.id}/">'
        self.assertEqual(
            find_forbidden_references(markdown, self.alice),
            [f"/api/library/files/{other.id}/"],
        )

    def test_raw_html_srcset_is_checked(self):
        markdown = '<img srcset="https://cdn.example.com/a.png 1x, /local/b.png 2x">'
        self.assertEqual(find_forbidden_references(markdown, self.alice), ["/local/b.png"])

    def test_code_is_ignored(self):
        markdown = "```\n![x](/media/private/a.png)\n```\nand `[y](/media/b.png)` inline"
        self.assertEqual(find_forbidden_references(markdown, self.alice), [])
