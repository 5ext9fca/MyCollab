"""Single entry point for every library write.

Uploads and deletes go through these functions so size/type limits and the
owner-only delete rule are enforced in one place, reusable by the API, admin
and future clients.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import transaction

from common.exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure

from .models import LibraryFile

# Extension -> served content type. Derived from the whitelist, never from the
# client, so an upload cannot masquerade as HTML or JavaScript.
CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "zip": "application/zip",
    "txt": "text/plain; charset=utf-8",
    "md": "text/plain; charset=utf-8",
}


def allowed_extensions() -> list[str]:
    """Sorted whitelist, so callers can show what is accepted."""
    return sorted({ext.lower().lstrip(".") for ext in settings.LIBRARY_ALLOWED_EXTENSIONS})


def max_upload_bytes() -> int:
    return int(settings.LIBRARY_MAX_UPLOAD_BYTES)


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower().lstrip(".")


@transaction.atomic
def save_library_file(*, actor, upload) -> LibraryFile:
    name = Path(getattr(upload, "name", "") or "").name
    if not name:
        raise ValidationFailure("缺少文件名。", field_errors={"file": ["缺少文件名。"]})

    allowed = allowed_extensions()
    extension = _extension(name)
    if extension not in allowed:
        raise ValidationFailure(
            f"不支持的文件类型，仅允许：{', '.join(allowed)}。",
            field_errors={"file": [f".{extension} 不在允许的类型内。"]},
        )

    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0:
        raise ValidationFailure("文件内容为空。", field_errors={"file": ["文件内容为空。"]})

    limit = max_upload_bytes()
    if size > limit:
        raise ValidationFailure(
            f"文件过大，单文件不得超过 {limit // (1024 * 1024)} MB。",
            field_errors={"file": [f"文件超过 {limit} 字节上限。"]},
        )

    record = LibraryFile(
        owner=actor,
        original_name=name[:255],
        content_type=CONTENT_TYPES.get(extension, "application/octet-stream"),
        size=size,
    )
    record.file.save(name, upload, save=False)
    record.save()
    return record


@transaction.atomic
def delete_library_file(*, actor, file_id) -> None:
    try:
        record = LibraryFile.objects.select_for_update().get(pk=file_id)
    except LibraryFile.DoesNotExist:
        raise NotFound("文件不存在。")

    if record.owner_id != actor.pk:
        raise PermissionDenied("只有文件所有者可以删除该文件。")
    if record.execution_candidates.exists():
        raise ConflictError("文件已关联委派成果，须保留执行与提交历史，不能删除。")

    storage = record.file.storage
    stored_name = record.file.name
    record.delete()
    storage.delete(stored_name)
