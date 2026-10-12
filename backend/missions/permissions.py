"""Backward-compatible re-export of the shared team-member permission.

The canonical definition lives in :mod:`common.permissions` so other apps
(for example ``library``) can reuse it without importing from ``missions``.
Existing ``from missions.permissions import IsTeamMember`` imports keep working.
"""

from common.permissions import IsTeamMember  # noqa: F401

__all__ = ["IsTeamMember"]
