import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def library_upload_to(instance, filename: str) -> str:
    """Store an upload under ``library/<owner_id>/<uuid><ext>``.

    The client-supplied name is discarded (the original is kept in the DB), so
    two users can never collide and a crafted name can never escape the
    owner's directory.
    """
    suffix = Path(filename or "").suffix.lower()
    if len(suffix) > 16:
        suffix = ""
    return f"library/{instance.owner_id}/{uuid.uuid4().hex}{suffix}"


class LibraryFile(models.Model):
    """A file uploaded by one user into their personal library.

    Reads are team-wide (any authenticated member may download), but Markdown
    may only reference the author's own files or external URLs. That rule is
    enforced at write time by :mod:`library.references`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_files",
    )
    file = models.FileField(upload_to=library_upload_to, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "-created_at"])]

    @property
    def url(self) -> str:
        """Authorized download URL used to reference the file in Markdown."""
        return f"/api/library/files/{self.id}/"

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.original_name}"
