"""Backward-compatible re-export of the shared domain errors.

The canonical definitions live in :mod:`common.exceptions` so that other apps
(for example ``accounts``) can reuse them without importing from ``missions``.
Existing ``from missions.exceptions import ...`` imports keep working.
"""

from common.exceptions import (  # noqa: F401
    ConflictError,
    DomainError,
    NotFound,
    PermissionDenied,
    ValidationFailure,
)

__all__ = [
    "DomainError",
    "ValidationFailure",
    "PermissionDenied",
    "NotFound",
    "ConflictError",
]
