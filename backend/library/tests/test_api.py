import os
import tempfile
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from library.models import LibraryFile

MEDIA_ROOT = tempfile.mkdtemp(prefix="mycollab-library-tests-")


def png_bytes(size: int = 8) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, size - 8)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class LibraryApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.client = APIClient()

    def upload(self, name="shot.png", content=None, user=None):
        if user is not None:
            self.client.force_authenticate(user)
        payload = png_bytes() if content is None else content
        return self.client.post(
            "/api/library/files/",
            {"file": SimpleUploadedFile(name, payload)},
            format="multipart",
        )

    def test_upload_and_download(self):
        self.client.force_authenticate(self.alice)
        response = self.upload()

        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["original_name"], "shot.png")
        self.assertEqual(data["content_type"], "image/png")
        self.assertEqual(data["size"], len(png_bytes()))
        self.assertEqual(data["url"], f"/api/library/files/{data['id']}/")

        record = LibraryFile.objects.get(pk=data["id"])
        self.assertEqual(record.owner, self.alice)
        # Stored under the owner's directory with a generated name.
        self.assertTrue(record.file.name.startswith(f"library/{self.alice.id}/"))
        self.assertNotIn("shot.png", record.file.name)

    def test_any_member_may_download(self):
        file_id = self.upload(user=self.alice).json()["id"]

        self.client.force_authenticate(self.bob)
        download = self.client.get(f"/api/library/files/{file_id}/")

        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), png_bytes())
        self.assertEqual(download["Content-Type"], "image/png")
        self.assertIn("inline", download["Content-Disposition"])
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")

    def test_non_image_is_downloaded_as_attachment(self):
        self.client.force_authenticate(self.alice)
        created = self.upload(name="notes.md", content="# hi".encode())

        self.assertEqual(created.json()["content_type"], "text/plain; charset=utf-8")
        download = self.client.get(created.json()["url"])
        self.assertIn("attachment", download["Content-Disposition"])

    def test_list_only_returns_own_files(self):
        self.upload(name="a.png", user=self.alice)
        self.upload(name="b.png", user=self.bob)

        self.client.force_authenticate(self.alice)
        body = self.client.get("/api/library/files/").json()

        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["original_name"], "a.png")

    def test_rejects_disallowed_extension(self):
        self.client.force_authenticate(self.alice)
        response = self.upload(name="evil.exe", content=b"MZ")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertIn("file", response.json()["field_errors"])
        self.assertFalse(LibraryFile.objects.exists())

    @override_settings(LIBRARY_MAX_UPLOAD_BYTES=16)
    def test_rejects_oversized_file(self):
        self.client.force_authenticate(self.alice)
        response = self.upload(name="big.png", content=png_bytes(64))

        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.json()["field_errors"])
        self.assertFalse(LibraryFile.objects.exists())

    def test_owner_deletes_own_file(self):
        record = LibraryFile.objects.get(pk=self.upload(user=self.alice).json()["id"])
        stored_path = record.file.path
        self.assertTrue(os.path.exists(stored_path))

        self.client.force_authenticate(self.alice)
        response = self.client.delete(f"/api/library/files/{record.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(LibraryFile.objects.filter(pk=record.id).exists())
        self.assertFalse(os.path.exists(stored_path))

    def test_non_owner_cannot_delete(self):
        file_id = self.upload(user=self.alice).json()["id"]

        self.client.force_authenticate(self.bob)
        response = self.client.delete(f"/api/library/files/{file_id}/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")
        self.assertTrue(LibraryFile.objects.filter(pk=file_id).exists())

    def test_anonymous_is_rejected(self):
        file_id = self.upload(user=self.alice).json()["id"]
        url = f"/api/library/files/{file_id}/"
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get("/api/library/files/").status_code, 403)
        self.assertEqual(self.client.post("/api/library/files/").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)

    def test_unknown_file_is_404(self):
        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.get(f"/api/library/files/{uuid.uuid4()}/").status_code, 404
        )

    def test_missing_blob_is_404(self):
        record = LibraryFile.objects.get(pk=self.upload(user=self.alice).json()["id"])
        os.remove(record.file.path)

        self.client.force_authenticate(self.bob)
        response = self.client.get(f"/api/library/files/{record.id}/")

        self.assertEqual(response.status_code, 404)
