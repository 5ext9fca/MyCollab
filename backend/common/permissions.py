"""Shared DRF permissions usable by any app.

Keeping this in ``common`` lets apps such as ``library`` reuse the team-member
permission without importing from ``missions`` (which would create a circular
app dependency).
"""

from rest_framework.permissions import BasePermission


class IsTeamMember(BasePermission):
    """All authenticated users are team members.

    This is a single-team MVP, so reads are team-wide. Per-operation write
    permissions are enforced in the service layer rather than here, which keeps
    the rules reusable by admin actions and management commands.
    """

    message = "需要登录后才能访问。"

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)
