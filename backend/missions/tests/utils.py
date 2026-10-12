"""Shared helpers for mission service tests.

Every write now requires ``expected_version``. These wrappers fetch the current
version (and, for reviews, the current submission) so tests stay readable.
"""

from __future__ import annotations

from missions import services
from missions.models import Mission


def version_of(mission) -> int:
    return Mission.objects.values_list("version", flat=True).get(pk=mission.id)


def fresh(mission) -> Mission:
    return Mission.objects.get(pk=mission.id)


def claim(actor, mission):
    return services.claim_mission(
        actor=actor, mission_id=mission.id, expected_version=version_of(mission)
    )


def release(actor, mission):
    return services.release_mission(
        actor=actor, mission_id=mission.id, expected_version=version_of(mission)
    )


def submit(actor, mission, description: str = "成果", **kwargs):
    kwargs.setdefault("verification_description", "人工验证：通过")
    return services.submit_mission(
        actor=actor,
        mission_id=mission.id,
        description=description,
        expected_version=version_of(mission),
        **kwargs,
    )


def review(actor, mission, decision: str = "accept", submission_id=None, comment=None, **kwargs):
    if submission_id is None:
        submission_id = Mission.objects.values_list(
            "current_submission_id", flat=True
        ).get(pk=mission.id)
    if comment is None:
        comment = "人工验证通过" if decision != "reject" else "退回"
    return services.review_mission(
        actor=actor,
        mission_id=mission.id,
        submission_id=submission_id,
        decision=decision,
        comment=comment,
        expected_version=version_of(mission),
        **kwargs,
    )


def cancel(actor, mission, reason: str = ""):
    return services.cancel_mission(
        actor=actor,
        mission_id=mission.id,
        reason=reason,
        expected_version=version_of(mission),
    )


def update(actor, mission, changes: dict):
    return services.update_mission(
        actor=actor,
        mission_id=mission.id,
        expected_version=version_of(mission),
        changes=changes,
    )
