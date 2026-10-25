"""Shared queryset filters for mission lists.

Both the paginated ``/api/missions/`` list and the read-only workspace
aggregations use these filters so the two entry points cannot drift apart.
Filtering is purely read-side; every write still goes through
``missions/services.py``.
"""

from __future__ import annotations

import uuid

from django.db.models import Exists, OuterRef, Q

from .exceptions import ValidationFailure
from .models import (
    Mission,
    MissionDependency,
    MissionPriority,
    MissionStatus,
    MissionType,
)

#: Columns a client may sort by; the leading ``-`` flips the direction.
ORDERING_FIELDS = {"created_at", "updated_at", "title", "status", "priority", "type"}

#: Statuses that count as "still open work" for the derived blocked flag.
OPEN_STATUSES = [MissionStatus.OPEN, MissionStatus.IN_PROGRESS, MissionStatus.SUBMITTED]


def parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationFailure(
            f"无效的 {field} 参数。", field_errors={field: ["不是合法的 UUID。"]}
        )


def parse_user_id(value, field):
    if not isinstance(value, str) or not value.isdecimal() or int(value) < 1:
        raise ValidationFailure('成员 ID 须为正整数。', field_errors={field: ['不是合法成员 ID。']})
    return int(value)


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value, field: str, *, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationFailure(f"无效的 {field} 参数。", field_errors={field: ["不是整数。"]})
    return max(minimum, min(maximum, parsed))


def _unresolved_prerequisites_for_outer():
    """``EXISTS`` subquery: the outer mission has an unfinished prerequisite."""
    return MissionDependency.objects.filter(mission=OuterRef("pk")).exclude(
        prerequisite__status=MissionStatus.DONE
    )


def apply_mission_filters(qs, params, user):
    """Return ``qs`` narrowed by the request's query parameters.

    Supported params: ``status``, ``type``, ``priority``, ``milestone``,
    ``blocked``, ``revalidation``, ``tag`` (repeatable/AND), ``creator``,
    ``assignee``, ``reviewer``, ``parent``, ``search``/``q`` and ``ordering``.
    Unknown values for enum-ish params raise ``ValidationFailure`` (400).
    """

    def get(name: str):
        value = params.get(name)
        if value is None:
            return None
        value = value.strip()
        return value or None

    status = get("status")
    if status:
        if status not in MissionStatus.values:
            raise ValidationFailure(
                "无效的 status 参数。", field_errors={"status": ["未知状态。"]}
            )
        qs = qs.filter(status=status)

    mission_type = get("type")
    if mission_type:
        if mission_type not in MissionType.values:
            raise ValidationFailure(
                "无效的 type 参数。", field_errors={"type": ["未知类型。"]}
            )
        qs = qs.filter(type=mission_type)

    priority = get("priority")
    if priority:
        if priority not in MissionPriority.values:
            raise ValidationFailure(
                "无效的 priority 参数。", field_errors={"priority": ["未知优先级。"]}
            )
        qs = qs.filter(priority=priority)

    production_batch = get("production_batch")
    if production_batch == "none":
        qs = qs.filter(production_item__isnull=True)
    elif production_batch:
        qs = qs.filter(production_item__batch_id=parse_uuid(production_batch, "production_batch"))

    design_element = get("design_element")
    if design_element:
        qs = qs.filter(design_element_id=None if design_element == "none" else parse_uuid(design_element, "design_element"))

    milestone = get("milestone")
    if milestone:
        if milestone in {"none", "null"}:
            qs = qs.filter(milestone__isnull=True)
        else:
            qs = qs.filter(milestone_id=parse_uuid(milestone, "milestone"))

    blocked = get("blocked")
    if blocked is not None:
        qs = qs.annotate(_has_unresolved=Exists(_unresolved_prerequisites_for_outer()))
        open_states = Q(status__in=OPEN_STATUSES)
        if parse_bool(blocked):
            qs = qs.filter(open_states, _has_unresolved=True)
        else:
            qs = qs.filter(~open_states | Q(_has_unresolved=False))

    # ``revalidation`` selects Done missions whose prerequisites are no longer met
    # (F1: "前置任务已不满足，需复核"). Kept separate from ``blocked`` because a
    # Done mission is not "blocked" but still needs a manual re-check.
    revalidation = get("revalidation")
    if revalidation is not None:
        qs = qs.annotate(_has_unresolved_review=Exists(_unresolved_prerequisites_for_outer()))
        condition = Q(status=MissionStatus.DONE, _has_unresolved_review=True)
        qs = qs.filter(condition if parse_bool(revalidation) else ~condition)

    # Multi-tag filter: repeat the parameter (?tag=a&tag=b) or use commas
    # (?tag=a,b). Multiple tags are ANDed, so a mission must carry every
    # requested tag. Each name gets its own filter() to force a separate
    # join on the M2M table; the caller applies distinct().
    tag_names = [
        name.strip() for raw in params.getlist("tag") for name in raw.split(",")
    ]
    for name in dict.fromkeys(name for name in tag_names if name):
        qs = qs.filter(tags__name=name)

    creator = get("creator")
    if creator == "me":
        qs = qs.filter(creator=user)
    elif creator == "none":
        qs = qs.filter(creator__isnull=True)
    elif creator:
        qs = qs.filter(creator_id=parse_user_id(creator, "creator"))

    for field in ("assignee", "reviewer"):
        raw = get(field)
        if not raw:
            continue
        if raw == "me":
            qs = qs.filter(**{field: user})
        elif raw == "none":
            qs = qs.filter(**{f"{field}__isnull": True})
        else:
            qs = qs.filter(**{f"{field}_id": parse_user_id(raw, field)})

    parent = get("parent")
    if parent == "root":
        qs = qs.filter(parent__isnull=True)
    elif parent:
        qs = qs.filter(parent_id=parse_uuid(parent, "parent"))

    # ``q`` is the workspace spelling; ``search`` stays for the list endpoint.
    search = get("q") or get("search")
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))

    ordering = get("ordering")
    if ordering and ordering.lstrip("-") in ORDERING_FIELDS:
        # Keep a stable order for equal priorities (creation time + id).
        qs = qs.order_by(ordering, "-created_at", "-id")

    from .scheduling import date_window, filter_schedule
    window = date_window(params)
    if window:
        qs = filter_schedule(qs, *window)
    return qs.distinct()


__all__ = [
    "ORDERING_FIELDS",
    "OPEN_STATUSES",
    "apply_mission_filters",
    "parse_bool",
    "parse_int",
    "parse_uuid",
]
