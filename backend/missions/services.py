"""Single entry point for every business write.

Views, admin actions and future clients must go through these functions. Each
function takes the actor explicitly and re-checks permissions, the current
status and data constraints inside a transaction, so an operation can never be
performed by patching a field directly.
"""

from __future__ import annotations

from typing import Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django.utils import timezone
from urllib.parse import urlsplit

from library.references import assert_markdown_references_allowed

from .exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from .models import (
    BuildStatus,
    Comment,
    DesignElement,
    DesignElementDependency,
    DesignElementEvent,
    ProductionTemplate,
    ProductionTemplateEvent,
    ProductionBatch,
    ProductionBatchItem,
    Milestone,
    MilestoneEvent,
    MilestoneEventAction,
    MilestoneStatus,
    Mission,
    MissionDependency,
    MissionEvent,
    MissionEventAction,
    MissionPriority,
    MissionStatus,
    MissionSubmission,
    MissionType,
    SubmissionBuildReference,
    SubmissionOutcome,
    SubmissionProvider,
    SubmissionSourceReference,
    Tag,
    MILESTONE_ACCEPTING_STATUSES,
    EDITABLE_STATUSES,
)

_UNSET = object()
FROZEN_STATUSES = {MissionStatus.SUBMITTED, MissionStatus.DONE}

#: One fixed advisory-lock key serialises the graph- and completion-changing
#: writes for the single team (see TECH_STACK.md section 6). The lock is
#: transaction-scoped and released on commit/rollback.
TEAM_OPS_LOCK_KEY = 0x4D59434F4C4C4142


# --------------------------------------------------------------------------- #
# Transactions / locking
# --------------------------------------------------------------------------- #
def _acquire_team_lock() -> None:
    """Serialize structural writes for the team.

    Taken *before* reading constraints and writing so two concurrent operations
    (dependency vs dependency, milestone completion vs reassignment, ...) cannot
    both validate against a stale graph.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [TEAM_OPS_LOCK_KEY])


def _notify_dependency_changes(func):
    """在团队锁内比较直接邻接风险，通知与业务事务一起回滚。"""
    from functools import wraps

    @wraps(func)
    def wrapped(*args, **kwargs):
        from notifications.services import dependency_snapshot, dependency_changes
        _acquire_team_lock()
        before = dependency_snapshot(kwargs['mission_id'])
        result = func(*args, **kwargs)
        event = MissionEvent.objects.filter(mission_id=kwargs['mission_id']).order_by('-pk').first()
        dependency_changes(before, actor=kwargs['actor'], source_event=event)
        return result
    return wrapped


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get_locked(mission_id) -> Mission:
    try:
        return Mission.objects.select_for_update().get(pk=mission_id)
    except Mission.DoesNotExist:
        raise NotFound("任务不存在。")


def _get_mission(mission_id) -> Mission:
    """Read-only fetch used by writes that do not change the mission row."""
    try:
        return Mission.objects.get(pk=mission_id)
    except Mission.DoesNotExist:
        raise NotFound("任务不存在。")


def _get_locked_comment(comment_id) -> Comment:
    try:
        return Comment.objects.select_for_update().get(pk=comment_id)
    except Comment.DoesNotExist:
        raise NotFound("评论不存在。")


def _get_locked_milestone(milestone_id) -> Milestone:
    try:
        return Milestone.objects.select_for_update().get(pk=milestone_id)
    except Milestone.DoesNotExist:
        raise NotFound("里程碑不存在。")


def _record_event(mission: Mission, actor, action: str, payload: dict | None = None) -> None:
    from notifications.services import from_event
    event = MissionEvent.objects.create(mission=mission, actor=actor, action=action, payload=payload or {})
    from_event(event)


def _record_milestone_event(
    milestone: Milestone, actor, action: str, payload: dict | None = None
) -> None:
    MilestoneEvent.objects.create(
        milestone=milestone, actor=actor, action=action, payload=payload or {}
    )


def _apply_tags(mission: Mission, tag_names: Iterable[str] | None) -> None:
    if tag_names is None:
        return
    tags = []
    for raw in tag_names:
        name = raw.strip()
        if not name:
            continue
        tag, _ = Tag.objects.get_or_create(name__iexact=name, defaults={"name": name})
        tags.append(tag)
    mission.tags.set(tags)


def _is_admin(actor) -> bool:
    return bool(getattr(actor, "is_staff", False))


def _check_version(mission: Mission, expected_version) -> None:
    if expected_version is None:
        raise ValidationFailure("缺少 expected_version。", field_errors={"expected_version": ["必填。"]})
    if mission.version != expected_version:
        raise ConflictError("数据已被他人修改，请刷新后重试。", code="version_conflict")


def _is_active_member(user) -> bool:
    return user is not None and getattr(user, "is_active", False)


def _get_active_reviewer(reviewer_id):
    from accounts.models import User

    try:
        user = User.objects.get(pk=reviewer_id)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ValidationFailure("验收者不存在。", field_errors={"reviewer_id": ["用户不存在。"]})
    if not user.is_active:
        raise ValidationFailure("验收者必须是有效成员。", field_errors={"reviewer_id": ["用户无效。"]})
    return user


def _resolve_milestone(milestone_id, *, require_accepting: bool) -> Milestone | None:
    if milestone_id in (None, ""):
        return None
    try:
        milestone = Milestone.objects.get(pk=milestone_id)
    except (Milestone.DoesNotExist, ValueError, TypeError):
        raise ValidationFailure("里程碑不存在。", field_errors={"milestone_id": ["里程碑不存在。"]})
    if require_accepting and milestone.status not in MILESTONE_ACCEPTING_STATUSES:
        raise ConflictError(
            "只有 Planned / Active 的里程碑可以接收任务。", code="milestone_not_accepting"
        )
    return milestone


def _validate_http_url(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValidationFailure(
            "链接必须是 http(s) 外链。", field_errors={field: ["链接格式不合法。"]}
        )
    if parsed.username or parsed.password:
        raise ValidationFailure(
            "链接不能包含访问凭据。", field_errors={field: ["不允许带凭据的链接。"]}
        )
    return value


# --------------------------------------------------------------------------- #
# Dependency graph
# --------------------------------------------------------------------------- #
def _graph_adjacency() -> dict:
    """Return ``must_complete_before`` edges.

    Explicit dependency edges are ``prerequisite -> dependent``; the implicit
    completion edge is ``child -> parent`` (a child must finish before its
    parent can). Only checking the dependency table alone would miss the
    combined parent/dependency cycles.
    """
    adjacency: dict = {}
    for child_id, parent_id in Mission.objects.exclude(parent__isnull=True).values_list(
        "id", "parent_id"
    ):
        adjacency.setdefault(child_id, set()).add(parent_id)
    for prerequisite_id, dependent_id in MissionDependency.objects.values_list(
        "prerequisite_id", "mission_id"
    ):
        adjacency.setdefault(prerequisite_id, set()).add(dependent_id)
    return adjacency


def _reaches(adjacency: dict, start, target) -> bool:
    stack = [start]
    seen: set = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return False


def _assert_edge_allowed(adjacency: dict, source, target) -> None:
    """Reject adding edge ``source -> target`` if it would close a cycle."""
    if source == target:
        raise ConflictError("任务不能依赖自身。", code="dependency_cycle")
    if _reaches(adjacency, target, source):
        raise ConflictError("该操作会形成循环依赖。", code="dependency_cycle")


# --------------------------------------------------------------------------- #
# Derived (read-only) state
# --------------------------------------------------------------------------- #
def unfinished_prerequisites(mission: Mission):
    """Direct prerequisites that are not ``Done`` (``Cancelled`` still blocks)."""
    return Mission.objects.filter(dependents__mission_id=mission.id).exclude(
        status=MissionStatus.DONE
    )


def active_children(mission: Mission):
    """Effective direct children; cancelled children do not block the parent."""
    return mission.children.exclude(status=MissionStatus.CANCELLED)


def derived_state(mission: Mission) -> dict:
    """F1/F3 derived flags exposed by the API (never stored)."""
    blocking_ids = list(
        unfinished_prerequisites(mission).values_list("id", flat=True)
    )
    unfinished_children = list(
        mission.children.exclude(status__in=[MissionStatus.DONE, MissionStatus.CANCELLED])
        .values_list("id", flat=True)
    )
    has_unresolved = bool(blocking_ids)
    is_blocked = mission.status in (
        MissionStatus.OPEN,
        MissionStatus.IN_PROGRESS,
        MissionStatus.SUBMITTED,
    ) and has_unresolved

    reviewer = mission.reviewer
    reviewer_missing = reviewer is None or not reviewer.is_active
    milestone_closed = bool(
        mission.milestone_id
        and mission.milestone.status in (MilestoneStatus.COMPLETED, MilestoneStatus.CANCELLED)
    )
    return {
        "has_unresolved_prerequisites": has_unresolved,
        "is_blocked": is_blocked,
        "blocking_mission_ids": [str(pk) for pk in blocking_ids],
        "unfinished_child_ids": [str(pk) for pk in unfinished_children],
        "needs_dependency_review": mission.status == MissionStatus.DONE and has_unresolved,
        "reviewer_missing": reviewer_missing,
        "milestone_closed": milestone_closed,
        **schedule_risks_bulk([mission])[mission.pk],
    }


def derived_state_bulk(missions: Iterable[Mission], *, today=None) -> dict:
    """Batch version of :func:`derived_state` keyed by mission id.

    The workspace endpoints render whole boards and graphs; querying each node
    separately would be a glaring N+1. Two aggregate queries cover every node.
    """
    missions = list(missions)
    ids = [mission.id for mission in missions]
    if not ids:
        return {}

    blocking: dict = {}
    for mission_id, prerequisite_id, status in MissionDependency.objects.filter(
        mission_id__in=ids
    ).values_list("mission_id", "prerequisite_id", "prerequisite__status"):
        if status != MissionStatus.DONE:
            blocking.setdefault(mission_id, []).append(str(prerequisite_id))

    unfinished_children: dict = {}
    for parent_id, child_id in (
        Mission.objects.filter(parent_id__in=ids)
        .exclude(status__in=[MissionStatus.DONE, MissionStatus.CANCELLED])
        .values_list("parent_id", "id")
    ):
        unfinished_children.setdefault(parent_id, []).append(str(child_id))

    risks = schedule_risks_bulk(missions, today=today)
    result: dict = {}
    for mission in missions:
        blocking_ids = blocking.get(mission.id, [])
        has_unresolved = bool(blocking_ids)
        is_blocked = has_unresolved and mission.status in (
            MissionStatus.OPEN,
            MissionStatus.IN_PROGRESS,
            MissionStatus.SUBMITTED,
        )
        reviewer = mission.reviewer
        result[mission.id] = {
            **risks[mission.pk],
            "has_unresolved_prerequisites": has_unresolved,
            "is_blocked": is_blocked,
            "blocking_mission_ids": blocking_ids,
            "unfinished_child_ids": unfinished_children.get(mission.id, []),
            "needs_dependency_review": mission.status == MissionStatus.DONE and has_unresolved,
            "reviewer_missing": reviewer is None or not reviewer.is_active,
            "milestone_closed": bool(
                mission.milestone_id
                and mission.milestone.status
                in (MilestoneStatus.COMPLETED, MilestoneStatus.CANCELLED)
            ),
        }
    return result


def _assert_prerequisites_done(mission: Mission) -> None:
    if unfinished_prerequisites(mission).exists():
        raise ConflictError(
            "存在未完成的前置任务，无法提交或验收通过。", code="prerequisites_incomplete"
        )


def _assert_children_done(mission: Mission) -> None:
    if mission.children.exclude(status__in=[MissionStatus.DONE, MissionStatus.CANCELLED]).exists():
        raise ConflictError("仍有未完成的子任务。", code="children_incomplete")


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
def allowed_actions(user, mission: Mission) -> list[str]:
    """Server-computed capabilities the frontend uses to show buttons."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    is_creator = mission.creator_id == user.pk
    is_assignee = mission.assignee_id == user.pk
    is_reviewer = mission.reviewer_id == user.pk
    admin = _is_admin(user)
    state = derived_state(mission)
    actions: list[str] = []

    if mission.status == MissionStatus.OPEN and mission.assignee_id is None:
        actions.append("claim")
    if is_assignee and mission.status == MissionStatus.IN_PROGRESS:
        actions.extend(["release", "submit"])
    if (is_reviewer or admin) and mission.status == MissionStatus.SUBMITTED and not state["is_blocked"]:
        actions.append("review")
    if (is_creator or admin) and mission.status == MissionStatus.SUBMITTED:
        actions.append("transfer_review")
    if (is_creator or admin) and mission.status in EDITABLE_STATUSES:
        actions.extend(["edit", "cancel", "manage_dependencies"])
    if is_assignee and mission.status in EDITABLE_STATUSES:
        actions.append("manage_dependencies")
    if (is_creator or is_assignee) and mission.status not in (
        MissionStatus.DONE,
        MissionStatus.CANCELLED,
    ):
        actions.append("create_child")
    if (is_creator or is_reviewer or admin) and mission.status == MissionStatus.DONE:
        actions.append("reopen")
    return actions


def _assert_can_manage_dependencies(actor, mission: Mission) -> None:
    if mission.status not in EDITABLE_STATUSES:
        raise ConflictError("当前状态不允许修改依赖，请先退回可编辑状态。", code="mission_frozen")
    if actor.pk not in {mission.creator_id, mission.assignee_id} and not _is_admin(actor):
        raise PermissionDenied("只有发起者、当前认领者或管理员可以修改依赖。")


def _assert_can_add_child(actor, parent: Mission) -> None:
    if parent.status in FROZEN_STATUSES or parent.status == MissionStatus.CANCELLED:
        raise ConflictError("已完成或已取消的任务不能新增子任务。", code="parent_not_open")
    if actor.pk not in {parent.creator_id, parent.assignee_id}:
        raise PermissionDenied("只有任务的发起者或认领者可以新增子任务。")


# --------------------------------------------------------------------------- #
# Missions
# --------------------------------------------------------------------------- #
@transaction.atomic
def create_mission(
    *,
    actor,
    title: str,
    content: str = "",
    acceptance_criteria: str = "",
    tags: Iterable[str] | None = None,
    parent_id=None,
    type: str = MissionType.TASK,
    priority: str = MissionPriority.P2,
    reviewer_id=None,
    milestone_id=None,
    design_element_id=None,
    asset_ids=None,
    planned_start_date=None,
    planned_end_date=None,
) -> Mission:
    title = (title or "").strip()
    if not title:
        raise ValidationFailure("标题不能为空。", field_errors={"title": ["标题不能为空。"]})
    if type not in MissionType.values:
        raise ValidationFailure("无效的任务类型。", field_errors={"type": ["未知类型。"]})
    if priority not in MissionPriority.values:
        raise ValidationFailure("无效的优先级。", field_errors={"priority": ["未知优先级。"]})

    content = content or ""
    acceptance_criteria = acceptance_criteria or ""
    assert_markdown_references_allowed(content, actor, field="content")
    assert_markdown_references_allowed(acceptance_criteria, actor, field="acceptance_criteria")

    # Serialize with dependency/milestone/completion writes: assigning a
    # milestone must not race a milestone completion (see TECH_STACK.md §6).
    _acquire_team_lock()
    parent = None
    if parent_id is not None:
        parent = _get_locked(parent_id)
        _assert_can_add_child(actor, parent)

    reviewer = _get_active_reviewer(reviewer_id) if reviewer_id else actor
    if not _is_active_member(reviewer):
        raise ValidationFailure("验收者必须是有效成员。", field_errors={"reviewer_id": ["无效成员。"]})
    milestone = _resolve_milestone(milestone_id, require_accepting=True)
    planned_start_date, planned_end_date = _validate_schedule(planned_start_date, planned_end_date)

    mission = Mission.objects.create(
        title=title,
        content=content,
        acceptance_criteria=acceptance_criteria,
        creator=actor,
        parent=parent,
        status=MissionStatus.OPEN,
        type=type,
        priority=priority,
        reviewer=reviewer,
        milestone=milestone,
        design_element=_resolve_design_element(design_element_id, kind="Design"),
        planned_start_date=planned_start_date,
        planned_end_date=planned_end_date,
    )
    mission.assets.set(_resolve_assets(asset_ids or []))
    _apply_tags(mission, tags)
    _record_event(
        mission,
        actor,
        MissionEventAction.CREATED,
        {
            "parent_id": str(parent.id) if parent else None,
            "type": mission.type,
            "priority": mission.priority,
            "reviewer_id": str(reviewer.id),
            "milestone_id": str(milestone.id) if milestone else None,
        },
    )
    if parent is not None:
        _record_event(
            parent,
            actor,
            MissionEventAction.CHILD_CREATED,
            {"child_id": str(mission.id), "title": mission.title},
        )
    return mission


@transaction.atomic
def update_mission(*, actor, mission_id, expected_version: int, changes: dict) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    if mission.creator_id != actor.pk and not _is_admin(actor):
        raise PermissionDenied("只有发起者或管理员可以修改任务。")
    _check_version(mission, expected_version)
    if mission.status not in EDITABLE_STATUSES:
        raise ConflictError("当前状态已冻结内容，请先退回进行中再修改。", code="mission_frozen")

    changed_fields: list[str] = []

    if {"planned_start_date", "planned_end_date"} & changes.keys():
        start, end = _validate_schedule(changes.get("planned_start_date", mission.planned_start_date), changes.get("planned_end_date", mission.planned_end_date))
        before = _schedule_values(mission)
        mission.planned_start_date, mission.planned_end_date = start, end
        _assert_schedule_dependencies(mission)
        after = _schedule_values(mission)
        if before != after:
            _record_event(mission, actor, MissionEventAction.SCHEDULE_CHANGED, {"from": before, "to": after})
            changed_fields.extend(["planned_start_date", "planned_end_date"])

    if "design_element_id" in changes:
        target = changes["design_element_id"]
        if str(target or "") != str(mission.design_element_id or ""):
            old_id = mission.design_element_id
            mission.design_element = _resolve_design_element(target, kind="Design")
            _record_event(mission, actor, MissionEventAction.DESIGN_ELEMENT_CHANGED, {
                "from": str(old_id) if old_id else None,
                "to": str(mission.design_element_id) if mission.design_element_id else None,
            })
            changed_fields.append("design_element")

    if "asset_ids" in changes:
        before = sorted(str(pk) for pk in mission.assets.values_list("pk", flat=True))
        assets = _resolve_assets(changes["asset_ids"], retained=before)
        after = sorted(str(asset.pk) for asset in assets)
        batch_item = ProductionBatchItem.objects.filter(mission=mission).select_related("batch").first()
        if batch_item and str(batch_item.batch.asset_id) not in after:
            raise ConflictError("生产步骤不能解除所属资产。", code="production_asset_locked")
        if before != after:
            mission.assets.set(assets)
            _record_event(mission, actor, MissionEventAction.ASSETS_CHANGED, {"from": before, "to": after})
            changed_fields.append("assets")

    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise ValidationFailure("标题不能为空。", field_errors={"title": ["标题不能为空。"]})
        mission.title = title
        changed_fields.append("title")
    if "content" in changes:
        content = changes["content"] or ""
        assert_markdown_references_allowed(content, actor, field="content")
        mission.content = content
        changed_fields.append("content")
    if "acceptance_criteria" in changes:
        acceptance_criteria = changes["acceptance_criteria"] or ""
        assert_markdown_references_allowed(acceptance_criteria, actor, field="acceptance_criteria")
        mission.acceptance_criteria = acceptance_criteria
        changed_fields.append("acceptance_criteria")
    if "parent" in changes:
        new_parent_id = changes["parent"]
        if new_parent_id is None:
            mission.parent = None
        else:
            new_parent = _get_locked(new_parent_id)
            _assert_edge_allowed(_graph_adjacency(), mission.id, new_parent.id)
            if new_parent.status in FROZEN_STATUSES or new_parent.status == MissionStatus.CANCELLED:
                raise ConflictError("不能挂到已完成或已取消的任务下。", code="parent_not_open")
            if actor.pk not in {new_parent.creator_id, new_parent.assignee_id}:
                raise PermissionDenied("只有目标父任务的发起者或认领者可以建立该父子关系。")
            mission.parent = new_parent
        changed_fields.append("parent")
    if "tags" in changes:
        _apply_tags(mission, changes["tags"])
        changed_fields.append("tags")
    if "type" in changes:
        new_type = changes["type"]
        if new_type not in MissionType.values:
            raise ValidationFailure("无效的任务类型。", field_errors={"type": ["未知类型。"]})
        if new_type != mission.type:
            old_type, mission.type = mission.type, new_type
            _record_event(
                mission, actor, MissionEventAction.TYPE_CHANGED,
                {"from": old_type, "to": new_type},
            )
            changed_fields.append("type")
    if "priority" in changes:
        new_priority = changes["priority"]
        if new_priority not in MissionPriority.values:
            raise ValidationFailure("无效的优先级。", field_errors={"priority": ["未知优先级。"]})
        if new_priority != mission.priority:
            old_priority, mission.priority = mission.priority, new_priority
            _record_event(
                mission, actor, MissionEventAction.PRIORITY_CHANGED,
                {"from": old_priority, "to": new_priority},
            )
            changed_fields.append("priority")
    if "reviewer" in changes:
        reviewer = _get_active_reviewer(changes["reviewer"]) if changes["reviewer"] else None
        if reviewer is not None and reviewer.id != mission.reviewer_id:
            old_reviewer = mission.reviewer_id
            mission.reviewer = reviewer
            _record_event(
                mission, actor, MissionEventAction.REVIEWER_CHANGED,
                {"from": str(old_reviewer) if old_reviewer else None, "to": str(reviewer.id)},
            )
            changed_fields.append("reviewer")
    if "milestone" in changes:
        milestone = _resolve_milestone(changes["milestone"], require_accepting=True)
        new_id = milestone.id if milestone else None
        if new_id != mission.milestone_id:
            old_id = mission.milestone_id
            mission.milestone = milestone
            _record_event(
                mission, actor, MissionEventAction.MILESTONE_CHANGED,
                {
                    "from": str(old_id) if old_id else None,
                    "to": str(new_id) if new_id else None,
                },
            )
            changed_fields.append("milestone")

    mission.version += 1
    mission.save()
    if changed_fields:
        _record_event(
            mission, actor, MissionEventAction.UPDATED,
            {"fields": changed_fields, "version": mission.version},
        )
    return mission


@transaction.atomic
def claim_mission(*, actor, mission_id, expected_version) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    # Row lock + status/assignee guard: concurrent claims resolve to exactly one
    # winner, the loser sees the updated row and gets a 409.
    if mission.status != MissionStatus.OPEN or mission.assignee_id is not None:
        raise ConflictError("任务已被认领或状态已变化。", code="claim_conflict")
    mission.assignee = actor
    mission.status = MissionStatus.IN_PROGRESS
    mission.version += 1
    mission.save(update_fields=["assignee", "status", "version", "updated_at"])
    _record_event(mission, actor, MissionEventAction.CLAIMED)
    return mission


@transaction.atomic
def release_mission(*, actor, mission_id, expected_version) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    if mission.assignee_id != actor.pk:
        raise PermissionDenied("只有当前认领者可以退出。")
    if mission.status != MissionStatus.IN_PROGRESS:
        raise ConflictError("只有进行中的任务可以退出。", code="release_conflict")
    mission.assignee = None
    mission.status = MissionStatus.OPEN
    mission.version += 1
    mission.save(update_fields=["assignee", "status", "version", "updated_at"])
    _record_event(mission, actor, MissionEventAction.RELEASED)
    return mission


def _build_source_references(submission: MissionSubmission, references) -> None:
    for raw in references or []:
        provider = (raw.get("provider") or SubmissionProvider.GIT).strip()
        if provider not in SubmissionProvider.values:
            raise ValidationFailure(
                "无效的代码来源类型。", field_errors={"source_references": ["未知 provider。"]}
            )
        repository = (raw.get("repository") or "").strip()
        if not repository:
            raise ValidationFailure(
                "代码来源必须提供仓库名称。",
                field_errors={"source_references": ["repository 不能为空。"]},
            )
        revision = (raw.get("revision") or "").strip()
        if not revision:
            raise ValidationFailure(
                "代码来源必须提供 revision。",
                field_errors={"source_references": ["revision 不能为空。"]},
            )
        browse_url = _validate_http_url(raw.get("browse_url", ""), "source_references")
        SubmissionSourceReference.objects.create(
            submission=submission,
            provider=provider,
            repository=repository[:300],
            revision=revision[:200],
            browse_url=browse_url[:500],
        )


def _build_build_references(submission: MissionSubmission, references) -> None:
    for raw in references or []:
        provider = (raw.get("provider") or "").strip()
        if not provider:
            raise ValidationFailure(
                "构建来源必须提供 provider。",
                field_errors={"build_references": ["provider 不能为空。"]},
            )
        build_id = (raw.get("build_id") or "").strip()
        if not build_id:
            raise ValidationFailure(
                "构建必须提供 build_id。",
                field_errors={"build_references": ["build_id 不能为空。"]},
            )
        platform = (raw.get("platform") or "").strip()
        if not platform:
            raise ValidationFailure(
                "构建必须提供 platform。",
                field_errors={"build_references": ["platform 不能为空。"]},
            )
        status = (raw.get("status") or BuildStatus.UNKNOWN).strip()
        if status not in BuildStatus.values:
            raise ValidationFailure(
                "无效的构建结果。", field_errors={"build_references": ["未知 status。"]}
            )
        artifact_url = _validate_http_url(raw.get("artifact_url", ""), "build_references")
        SubmissionBuildReference.objects.create(
            submission=submission,
            provider=provider[:50],
            build_id=build_id[:100],
            platform=platform[:50],
            source_revision=(raw.get("source_revision") or "").strip()[:200],
            artifact_url=artifact_url[:500],
            status=status,
            verification_note=raw.get("verification_note") or "",
        )


@transaction.atomic
def submit_mission(
    *,
    actor,
    mission_id,
    description: str,
    verification_description: str = "",
    source_references=None,
    build_references=None,
    execution_candidate_ids=None,
    code_execution_ids=None,
    expected_version,
) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    if mission.assignee_id != actor.pk:
        raise PermissionDenied("只有认领者可以提交成果。")
    if mission.status != MissionStatus.IN_PROGRESS:
        raise ConflictError("只有进行中的任务可以提交。", code="submit_conflict")

    description = (description or "").strip()
    if not description:
        raise ValidationFailure("提交成果不能为空。", field_errors={"description": ["提交成果不能为空。"]})
    assert_markdown_references_allowed(description, actor, field="description")

    verification_description = (verification_description or "").strip()
    has_source = bool(source_references)
    has_build = bool(build_references)
    if not (has_source or has_build or verification_description):
        raise ValidationFailure(
            "必须提供源码引用、构建引用或人工验证说明之一。",
            field_errors={"verification_description": ["缺少验证证据。"]},
        )

    if mission.reviewer_id is None or not _is_active_member(mission.reviewer):
        raise ConflictError("验收者无效，请先重新指定验收者。", code="reviewer_missing")

    _assert_prerequisites_done(mission)
    _assert_children_done(mission)

    from .models import ExecutionCandidate, SubmissionExecutionArtifact
    candidate_ids = execution_candidate_ids or []
    if not isinstance(candidate_ids, list) or len(candidate_ids) > 20 or len(set(candidate_ids)) != len(candidate_ids):
        raise ValidationFailure("最多选择 20 项不重复的执行成果。")
    candidates = list(ExecutionCandidate.objects.filter(pk__in=candidate_ids).select_related('execution__request', 'execution__asset', 'file'))
    if len(candidates) != len(candidate_ids) or any(
        item.execution.mission_id != mission.pk or item.execution.actor_id != actor.pk or not item.file_id
        or item.file.owner_id != actor.pk or item.execution.request.status != 'succeeded'
        or item.execution.mission_version != mission.version
        or item.execution.asset.archived or item.execution.asset.version != item.execution.asset_version
        or not mission.assets.filter(pk=item.execution.asset_id).exists()
        for item in candidates
    ):
        raise ValidationFailure("执行成果不属于当前任务/认领者、尚未完成或任务版本已变化。")
    from .models import CodeExecution, SubmissionCodeExecution
    code_ids = code_execution_ids or []
    if not isinstance(code_ids, list) or len(code_ids) > 20 or len(set(code_ids)) != len(code_ids):
        raise ValidationFailure("最多选择 20 项不重复的代码成果。")
    code_results = list(CodeExecution.objects.filter(pk__in=code_ids).select_related('request', 'patch'))
    if len(code_results) != len(code_ids) or any(
        item.mission_id != mission.pk or item.actor_id != actor.pk or not item.patch_id
        or item.patch.owner_id != actor.pk or item.request.status != 'succeeded'
        or item.mission_version != mission.version for item in code_results
    ):
        raise ValidationFailure("代码成果未完成、不属于当前任务/本人或版本已过期。")
    submission = MissionSubmission.objects.create(
        mission=mission,
        submitted_by=actor,
        description=description,
        verification_description=verification_description,
        reviewer_snapshot=mission.reviewer,
        outcome=SubmissionOutcome.PENDING,
    )
    SubmissionCodeExecution.objects.bulk_create([
        SubmissionCodeExecution(submission=submission, execution=item) for item in code_results
    ])
    _build_source_references(submission, source_references)
    _build_build_references(submission, build_references)
    SubmissionExecutionArtifact.objects.bulk_create([
        SubmissionExecutionArtifact(submission=submission, candidate=item) for item in candidates
    ])

    mission.current_submission = submission
    mission.status = MissionStatus.SUBMITTED
    mission.version += 1
    mission.save(
        update_fields=["current_submission", "status", "version", "updated_at"]
    )
    _record_event(
        mission, actor, MissionEventAction.SUBMITTED, {"submission_id": str(submission.id)}
    )
    return mission


@transaction.atomic
@_notify_dependency_changes
def review_mission(
    *,
    actor,
    mission_id,
    submission_id,
    decision: str,
    comment: str = "",
    verified_build_reference_id=None,
    expected_version,
) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    if mission.reviewer_id != actor.pk and not _is_admin(actor):
        raise PermissionDenied("只有当前验收者或管理员可以验收。")
    if mission.status != MissionStatus.SUBMITTED:
        raise ConflictError("任务未处于待验收状态。", code="review_conflict")

    try:
        submission = MissionSubmission.objects.select_for_update().get(pk=submission_id)
    except (MissionSubmission.DoesNotExist, ValueError, TypeError):
        raise NotFound("提交记录不存在。")
    if (
        submission.mission_id != mission.id
        or mission.current_submission_id != submission.id
        or submission.outcome != SubmissionOutcome.PENDING
    ):
        raise ConflictError("只能验收当前待处理的提交。", code="submission_conflict")

    decision = (decision or "").strip().lower()
    comment = (comment or "").strip()
    if decision == "accept":
        approve = True
    elif decision == "reject":
        approve = False
    else:
        raise ValidationFailure("无效的验收决定。", field_errors={"decision": ["未知决定。"]})

    if approve:
        _assert_prerequisites_done(mission)
        _assert_children_done(mission)
        builds = list(submission.build_references.all())
        if builds:
            if not verified_build_reference_id:
                raise ValidationFailure(
                    "附带构建时必须选择所验证的构建版本。",
                    field_errors={"verified_build_reference_id": ["必填。"]},
                )
            try:
                verified = next(
                    b for b in builds if str(b.id) == str(verified_build_reference_id)
                )
            except StopIteration:
                raise ValidationFailure(
                    "所选构建不属于本次提交。",
                    field_errors={"verified_build_reference_id": ["不属于本次提交。"]},
                )
            if verified.status != BuildStatus.SUCCEEDED:
                raise ConflictError(
                    "只有构建成功的版本可以通过验收。", code="build_not_succeeded"
                )
        else:
            if verified_build_reference_id:
                raise ValidationFailure(
                    "没有构建时不能指定验证构建。",
                    field_errors={"verified_build_reference_id": ["应留空。"]},
                )
            if not comment:
                raise ValidationFailure(
                    "没有构建时必须填写人工验证说明。",
                    field_errors={"comment": ["必填。"]},
                )
            verified = None

        submission.outcome = SubmissionOutcome.ACCEPTED
        submission.reviewed_by = actor
        submission.reviewed_at = timezone.now()
        submission.review_comment = comment
        submission.verified_build_reference = verified
        submission.save(
            update_fields=[
                "outcome",
                "reviewed_by",
                "reviewed_at",
                "review_comment",
                "verified_build_reference",
            ]
        )
        mission.status = MissionStatus.DONE
        action = MissionEventAction.REVIEW_APPROVED
        payload = {
            "submission_id": str(submission.id),
            "comment": comment,
            "verified_build_reference_id": str(verified.id) if verified else None,
        }
    else:
        if not comment:
            raise ValidationFailure(
                "退回时必须填写验收意见。", field_errors={"comment": ["必填。"]}
            )
        submission.outcome = SubmissionOutcome.REJECTED
        submission.reviewed_by = actor
        submission.reviewed_at = timezone.now()
        submission.review_comment = comment
        submission.save(
            update_fields=["outcome", "reviewed_by", "reviewed_at", "review_comment"]
        )
        mission.status = MissionStatus.IN_PROGRESS
        action = MissionEventAction.REVIEW_REJECTED
        payload = {"submission_id": str(submission.id), "comment": comment}

    mission.version += 1
    mission.save(update_fields=["status", "version", "updated_at"])
    _record_event(mission, actor, action, payload)
    return mission


@transaction.atomic
def transfer_review(
    *, actor, mission_id, new_reviewer_id, reason: str, expected_version
) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    if mission.creator_id != actor.pk and not _is_admin(actor):
        raise PermissionDenied("只有发起者或管理员可以转交验收。")
    if mission.status != MissionStatus.SUBMITTED:
        raise ConflictError("只有待验收的任务可以转交验收。", code="transfer_conflict")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailure("转交验收必须填写原因。", field_errors={"reason": ["必填。"]})
    reviewer = _get_active_reviewer(new_reviewer_id)
    old_reviewer_id = mission.reviewer_id
    mission.reviewer = reviewer
    mission.version += 1
    mission.save(update_fields=["reviewer", "version", "updated_at"])
    _record_event(
        mission,
        actor,
        MissionEventAction.REVIEW_TRANSFERRED,
        {
            "from": str(old_reviewer_id) if old_reviewer_id else None,
            "to": str(reviewer.id),
            "reason": reason,
        },
    )
    return mission


@transaction.atomic
@_notify_dependency_changes
def reopen_mission(*, actor, mission_id, reason: str, expected_version) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    if not (
        mission.creator_id == actor.pk
        or mission.reviewer_id == actor.pk
        or _is_admin(actor)
    ):
        raise PermissionDenied("只有发起者、当前验收者或管理员可以重新打开。")
    if mission.status != MissionStatus.DONE:
        raise ConflictError("只有已完成的任务可以重新打开。", code="reopen_conflict")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailure("重新打开必须填写原因。", field_errors={"reason": ["必填。"]})

    # A finished ancestor must be reopened top-down first: never leave a
    # "finished parent, running child" structure.
    node = mission.parent
    while node is not None:
        if node.status == MissionStatus.DONE:
            raise ConflictError(
                "上层任务已完成，请先从最上层向下重新打开相应祖先任务。",
                code="ancestor_done",
            )
        node = node.parent

    if mission.milestone_id and mission.milestone.status in (
        MilestoneStatus.COMPLETED,
        MilestoneStatus.CANCELLED,
    ):
        raise ConflictError(
            "目标里程碑已关闭，请先恢复里程碑。", code="milestone_closed"
        )

    old_status = mission.status
    if mission.assignee_id and _is_active_member(mission.assignee):
        mission.status = MissionStatus.IN_PROGRESS
    else:
        mission.assignee = None
        mission.status = MissionStatus.OPEN
    # Keep reviewer even if inactive; the API flags that it must be replaced.
    mission.current_submission = None
    mission.version += 1
    mission.save(
        update_fields=["assignee", "status", "current_submission", "version", "updated_at"]
    )
    _record_event(
        mission,
        actor,
        MissionEventAction.REOPENED,
        {
            "reason": reason,
            "from": old_status,
            "to": mission.status,
            "assignee_id": str(mission.assignee_id) if mission.assignee_id else None,
        },
    )
    return mission


@transaction.atomic
def cancel_mission(*, actor, mission_id, reason: str = "", expected_version) -> Mission:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    if mission.creator_id != actor.pk and not _is_admin(actor):
        raise PermissionDenied("只有发起者或管理员可以取消任务。")
    if mission.status not in (MissionStatus.OPEN, MissionStatus.IN_PROGRESS):
        raise ConflictError("只有待认领或进行中的任务可以取消。", code="cancel_conflict")

    reason = (reason or "").strip()
    if mission.parent_id is not None and not reason:
        raise ValidationFailure(
            "取消子任务必须填写原因。", field_errors={"reason": ["取消子任务必须填写原因。"]}
        )

    mission.status = MissionStatus.CANCELLED
    mission.version += 1
    mission.save(update_fields=["status", "version", "updated_at"])
    _record_event(mission, actor, MissionEventAction.CANCELLED, {"reason": reason})
    return mission


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #
@transaction.atomic
@_notify_dependency_changes
def add_dependency(*, actor, mission_id, prerequisite_id, expected_version) -> MissionDependency:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    _assert_can_manage_dependencies(actor, mission)

    if str(prerequisite_id) == str(mission.id):
        raise ValidationFailure("任务不能依赖自身。", field_errors={"prerequisite_id": ["不能自依赖。"]})
    try:
        prerequisite = Mission.objects.get(pk=prerequisite_id)
    except (Mission.DoesNotExist, ValueError, TypeError):
        raise NotFound("前置任务不存在。")

    if MissionDependency.objects.filter(mission=mission, prerequisite=prerequisite).exists():
        raise ConflictError("该依赖已存在。", code="dependency_exists")

    _assert_edge_allowed(_graph_adjacency(), prerequisite.id, mission.id)
    if mission.planned_end_date and prerequisite.planned_end_date and mission.planned_end_date < prerequisite.planned_end_date:
        raise ConflictError("任务的计划结束日期不得早于前置任务。", code="schedule_dependency_conflict")

    dependency = MissionDependency.objects.create(
        mission=mission, prerequisite=prerequisite, created_by=actor
    )
    mission.version += 1
    mission.save(update_fields=["version", "updated_at"])
    _record_event(
        mission,
        actor,
        MissionEventAction.DEPENDENCY_ADDED,
        {"prerequisite_id": str(prerequisite.id), "dependency_id": str(dependency.id)},
    )
    return dependency


@transaction.atomic
@_notify_dependency_changes
def remove_dependency(*, actor, mission_id, dependency_id, expected_version) -> None:
    _acquire_team_lock()
    mission = _get_locked(mission_id)
    _check_version(mission, expected_version)
    _assert_can_manage_dependencies(actor, mission)

    try:
        dependency = MissionDependency.objects.select_for_update().get(pk=dependency_id)
    except (MissionDependency.DoesNotExist, ValueError, TypeError):
        raise NotFound("依赖不存在。")
    if dependency.mission_id != mission.id:
        raise NotFound("依赖不存在。")

    prerequisite_id = dependency.prerequisite_id
    dependency.delete()
    mission.version += 1
    mission.save(update_fields=["version", "updated_at"])
    _record_event(
        mission,
        actor,
        MissionEventAction.DEPENDENCY_REMOVED,
        {"prerequisite_id": str(prerequisite_id)},
    )


# --------------------------------------------------------------------------- #
# Milestones
# --------------------------------------------------------------------------- #
@transaction.atomic
def create_milestone(*, actor, name: str, description: str = "", due_date=None) -> Milestone:
    name = (name or "").strip()
    if not name:
        raise ValidationFailure("里程碑名称不能为空。", field_errors={"name": ["名称不能为空。"]})
    milestone = Milestone.objects.create(
        name=name,
        description=description or "",
        due_date=due_date,
        created_by=actor,
        status=MilestoneStatus.PLANNED,
    )
    _record_milestone_event(
        milestone, actor, MilestoneEventAction.CREATED, {"name": milestone.name}
    )
    return milestone


@transaction.atomic
def update_milestone(*, actor, milestone_id, expected_version: int, changes: dict) -> Milestone:
    _acquire_team_lock()
    milestone = _get_locked_milestone(milestone_id)
    if milestone.created_by_id != actor.pk and not _is_admin(actor):
        raise PermissionDenied("只有创建者或管理员可以修改里程碑。")
    _check_version(milestone, expected_version)

    changed_fields: list[str] = []
    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise ValidationFailure("里程碑名称不能为空。", field_errors={"name": ["名称不能为空。"]})
        milestone.name = name
        changed_fields.append("name")
    if "description" in changes:
        milestone.description = changes["description"] or ""
        changed_fields.append("description")
    if "due_date" in changes:
        milestone.due_date = changes["due_date"]
        changed_fields.append("due_date")

    milestone.version += 1
    milestone.save()
    if changed_fields:
        _record_milestone_event(
            milestone, actor, MilestoneEventAction.UPDATED, {"fields": changed_fields}
        )
    return milestone


#: Allowed controlled transitions for a milestone.
MILESTONE_TRANSITIONS = {
    (MilestoneStatus.PLANNED, MilestoneStatus.ACTIVE),
    (MilestoneStatus.PLANNED, MilestoneStatus.CANCELLED),
    (MilestoneStatus.ACTIVE, MilestoneStatus.CANCELLED),
    (MilestoneStatus.ACTIVE, MilestoneStatus.COMPLETED),
    (MilestoneStatus.COMPLETED, MilestoneStatus.ACTIVE),
    (MilestoneStatus.CANCELLED, MilestoneStatus.ACTIVE),
}

#: Transitions that restore a closed milestone and therefore need a reason.
MILESTONE_RESTORE_TRANSITIONS = {
    (MilestoneStatus.COMPLETED, MilestoneStatus.ACTIVE),
    (MilestoneStatus.CANCELLED, MilestoneStatus.ACTIVE),
}


def milestone_progress(milestone: Milestone) -> dict:
    missions = list(milestone.missions.values_list("status", flat=True))
    effective = [s for s in missions if s != MissionStatus.CANCELLED]
    done = [s for s in effective if s == MissionStatus.DONE]
    total_effective = len(effective)
    progress = (len(done) / total_effective) if total_effective else None
    return {
        "total": len(missions),
        "effective_total": total_effective,
        "done": len(done),
        "progress": progress,
    }


@transaction.atomic
def transition_milestone(*, actor, milestone_id, status: str, expected_version, reason: str = "") -> Milestone:
    _acquire_team_lock()
    milestone = _get_locked_milestone(milestone_id)
    if milestone.created_by_id != actor.pk and not _is_admin(actor):
        raise PermissionDenied("只有创建者或管理员可以变更里程碑状态。")
    _check_version(milestone, expected_version)

    if status not in MilestoneStatus.values:
        raise ValidationFailure("无效的里程碑状态。", field_errors={"status": ["未知状态。"]})
    old_status = milestone.status
    if status == old_status:
        raise ConflictError("里程碑已处于该状态。", code="milestone_conflict")
    if (old_status, status) not in MILESTONE_TRANSITIONS:
        raise ConflictError("不允许的里程碑状态流转。", code="milestone_transition_invalid")

    reason = (reason or "").strip()
    if (old_status, status) in MILESTONE_RESTORE_TRANSITIONS and not reason:
        raise ValidationFailure("恢复里程碑必须记录原因。", field_errors={"reason": ["必填。"]})

    if status == MilestoneStatus.COMPLETED:
        effective = milestone.missions.exclude(status=MissionStatus.CANCELLED)
        if not effective.exists():
            raise ConflictError(
                "里程碑至少需要一个有效任务才能完成。", code="milestone_no_effective_tasks"
            )
        if effective.exclude(status=MissionStatus.DONE).exists():
            raise ConflictError(
                "仍有未完成的关联任务，无法完成里程碑。", code="milestone_tasks_incomplete"
            )

    milestone.status = status
    milestone.version += 1
    milestone.save(update_fields=["status", "version", "updated_at"])
    _record_milestone_event(
        milestone,
        actor,
        MilestoneEventAction.TRANSITIONED,
        {"from": old_status, "to": status, "reason": reason},
    )
    return milestone


# --------------------------------------------------------------------------- #
# Comments
# --------------------------------------------------------------------------- #
@transaction.atomic
def create_comment(*, actor, mission_id, content: str = "") -> Comment:
    """Any team member may comment on any mission, in any status."""
    _acquire_team_lock()
    mission = _get_mission(mission_id)
    content = content or ""
    assert_markdown_references_allowed(content, actor, field="content")
    from notifications.services import deliver
    comment = Comment.objects.create(mission=mission, author=actor, content=content)
    deliver(mission=mission, actor=actor, kind='comment_created', source_key=f'comment:{comment.pk}:created')
    return comment


@transaction.atomic
def update_comment(*, actor, comment_id, content: str) -> Comment:
    comment = _get_locked_comment(comment_id)
    if comment.author_id != actor.pk:
        raise PermissionDenied("只有作者可以编辑自己的评论。")
    content = content or ""
    assert_markdown_references_allowed(content, actor, field="content")
    comment.content = content
    comment.save(update_fields=["content", "updated_at"])
    return comment


@transaction.atomic
def delete_comment(*, actor, comment_id) -> None:
    comment = _get_locked_comment(comment_id)
    if comment.author_id != actor.pk:
        raise PermissionDenied("只有作者可以删除自己的评论。")
    comment.delete()


# 设计树写入与 Mission 结构变更共用团队事务锁。
def _resolve_design_element(element_id, *, kind=None):
    if element_id is None:
        return None
    try:
        element = DesignElement.objects.get(pk=element_id)
    except (DesignElement.DoesNotExist, ValueError, TypeError):
        raise ValidationFailure("设计条目不存在。", field_errors={"design_element_id": ["不存在。"]})
    if kind and element.kind != kind:
        raise ValidationFailure("关联条目类型不匹配。", field_errors={"design_element_id": ["请选择设计说明。"]})
    if element.archived:
        raise ConflictError("不能关联已归档的设计条目。", code="design_archived")
    return element


def _resolve_assets(asset_ids, *, retained=()):
    if not isinstance(asset_ids, (list, tuple)):
        raise ValidationFailure("相关资产必须为 ID 列表。", field_errors={"asset_ids": ["需要数组。"]})
    ids = {str(pk) for pk in asset_ids}
    try:
        assets = list(DesignElement.objects.filter(pk__in=ids))
    except (ValueError, TypeError, DjangoValidationError):
        raise ValidationFailure("资产 ID 无效。", field_errors={"asset_ids": ["无效 ID。"]})
    if len(assets) != len(ids) or any(asset.kind != "Asset" for asset in assets):
        raise ValidationFailure("相关资产不存在或类型错误。", field_errors={"asset_ids": ["只能引用资产。"]})
    if any(asset.archived and str(asset.pk) not in retained for asset in assets):
        raise ConflictError("不能新增已归档资产的引用。", code="design_archived")
    return assets


def _validate_design_parent(parent, kind):
    if parent and parent.kind != kind:
        raise ValidationFailure("设计与资产为同级对象，父条目必须属于同一类型。", field_errors={"parent": ["父条目类型不匹配。"]})
    return parent


def _set_design_prerequisites(element, prerequisite_ids):
    if not isinstance(prerequisite_ids, (list, tuple)):
        raise ValidationFailure("前置依赖必须为 ID 数组。", field_errors={"prerequisite_ids": ["需要数组。"]})
    ids = {str(pk) for pk in prerequisite_ids}
    try:
        targets = list(DesignElement.objects.filter(pk__in=ids))
    except (ValueError, TypeError, DjangoValidationError):
        raise ValidationFailure("前置依赖 ID 无效。", field_errors={"prerequisite_ids": ["无效 ID。"]})
    if len(targets) != len(ids) or any(target.kind != element.kind for target in targets):
        raise ValidationFailure("前置依赖必须是存在的同类型条目。", field_errors={"prerequisite_ids": ["设计只能依赖设计，资产只能依赖资产。"]})
    if str(element.pk) in ids:
        raise ConflictError("条目不能依赖自身。", code="design_dependency_cycle")
    retained = {str(pk) for pk in element.prerequisites.values_list("pk", flat=True)}
    if any(target.archived and str(target.pk) not in retained for target in targets):
        raise ConflictError("不能新增对已归档条目的依赖。", code="design_archived")
    # 父子结构只表达组成；循环检查仅遍历同类型的显式依赖边。
    adjacency = {}
    for source, target in DesignElementDependency.objects.filter(element__kind=element.kind).values_list("element_id", "prerequisite_id"):
        adjacency.setdefault(source, set()).add(target)
    pending = [target.pk for target in targets]
    visited = set()
    while pending:
        current = pending.pop()
        if current == element.pk:
            raise ConflictError("前置依赖不能形成循环。", code="design_dependency_cycle")
        if current not in visited:
            visited.add(current)
            pending.extend(adjacency.get(current, ()))
    element.prerequisites.set(targets)


def design_allowed_actions(actor, element):
    if not actor or not actor.is_active or (actor.pk != element.created_by_id and not _is_admin(actor)):
        return []
    return ["restore"] if element.archived else ["edit", "archive"]


def _design_title(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
        raise ValidationFailure("标题须为 1–200 字符。", field_errors={"title": ["标题长度不合法。"]})
    return value.strip()


@transaction.atomic
def create_design_element(*, actor, title, content="", kind="Design", parent=None, asset_ids=None, prerequisite_ids=None):
    _acquire_team_lock()
    if not _is_active_member(actor):
        raise PermissionDenied("只有有效团队成员可以创建设计条目。")
    if kind not in DesignElement.Kind.values:
        raise ValidationFailure("无效的设计条目类型。")
    assert_markdown_references_allowed(content, actor, field="content")
    element = DesignElement.objects.create(title=_design_title(title), content=content,
        kind=kind, parent=_validate_design_parent(_resolve_design_element(parent), kind), created_by=actor)
    if kind != "Design" and asset_ids:
        raise ValidationFailure("只有设计可以引用资产。")
    element.assets.set(_resolve_assets(asset_ids or []))
    _set_design_prerequisites(element, prerequisite_ids if prerequisite_ids is not None else [])
    DesignElementEvent.objects.create(element=element, actor=actor, action="created", payload={"prerequisite_ids": sorted(str(pk) for pk in element.prerequisites.values_list("pk", flat=True))})
    return element


@transaction.atomic
def update_design_element(*, actor, element_id, expected_version, changes):
    _acquire_team_lock()
    try:
        element = DesignElement.objects.select_for_update().select_related("created_by").get(pk=element_id)
    except DesignElement.DoesNotExist:
        raise NotFound("设计条目不存在。")
    if not design_allowed_actions(actor, element):
        raise PermissionDenied("只有创建者或管理员可以修改设计条目。")
    _check_version(element, expected_version)
    if set(changes) - {"title", "content", "parent", "archived", "asset_ids", "prerequisite_ids"}:
        raise ValidationFailure("包含不支持修改的字段。")
    if element.archived and changes != {"archived": False}:
        raise ConflictError("请先恢复设计条目再编辑。", code="design_archived")
    if "archived" in changes and not isinstance(changes["archived"], bool):
        raise ValidationFailure("归档状态必须是布尔值。")
    old = {"title": element.title, "content": element.content, "parent": str(element.parent_id) if element.parent_id else None, "archived": element.archived}
    old["asset_ids"] = sorted(str(pk) for pk in element.assets.values_list("pk", flat=True))
    old["prerequisite_ids"] = sorted(str(pk) for pk in element.prerequisites.values_list("pk", flat=True))
    if "prerequisite_ids" in changes:
        _set_design_prerequisites(element, changes["prerequisite_ids"])
    if "asset_ids" in changes:
        if element.kind != "Design" and changes["asset_ids"]:
            raise ValidationFailure("只有设计可以引用资产。")
        element.assets.set(_resolve_assets(changes["asset_ids"], retained=old["asset_ids"]))
    if "parent" in changes:
        parent = _validate_design_parent(_resolve_design_element(changes["parent"]), element.kind)
        cursor = parent
        while cursor:
            if cursor.pk == element.pk:
                raise ConflictError("设计树不能形成环。", code="design_cycle")
            cursor = cursor.parent
        element.parent = parent
    if changes.get("archived") is True and element.children.filter(archived=False).exists():
        raise ConflictError("请先归档所有子条目。", code="design_children_active")
    if changes.get("archived") is False and element.parent_id and element.parent.archived:
        raise ConflictError("请先恢复父条目。", code="design_archived")
    if "content" in changes:
        assert_markdown_references_allowed(changes["content"], element.created_by, field="content")
        element.content = changes["content"]
    if "title" in changes:
        element.title = _design_title(changes["title"])
    if "archived" in changes:
        element.archived = changes["archived"]
    element.version += 1
    element.save()
    new = {"title": element.title, "content": element.content, "parent": str(element.parent_id) if element.parent_id else None, "archived": element.archived}
    new["asset_ids"] = sorted(str(pk) for pk in element.assets.values_list("pk", flat=True))
    new["prerequisite_ids"] = sorted(str(pk) for pk in element.prerequisites.values_list("pk", flat=True))
    for field, action in (("prerequisite_ids", "dependencies_changed"), ("parent", "moved"), ("archived", "archived" if element.archived else "restored")):
        if old[field] != new[field]:
            DesignElementEvent.objects.create(element=element, actor=actor, action=action, payload={"from": old[field], "to": new[field]})
    DesignElementEvent.objects.create(element=element, actor=actor, action="updated", payload={"from": old, "to": new, "version": element.version})
    return element


# 模板仅保存生产说明，实例化后全部工作继续走 Mission 服务。
def _validate_template_steps(steps):
    import re
    from library.references import iter_references, LIBRARY_PATH_PREFIX

    if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
        raise ValidationFailure("模板必须包含 1–30 个步骤。", field_errors={"steps": ["步骤数量不合法。"]})
    normalized = []
    keys = set()
    allowed = {"key", "title", "content", "acceptance_criteria", "type", "priority", "tags", "prerequisite_keys"}
    for step in steps:
        if not isinstance(step, dict) or set(step) - allowed:
            raise ValidationFailure("步骤包含未知字段或格式错误。")
        key = step.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,50}", key) or key in keys:
            raise ValidationFailure("步骤 key 须唯一，且只含 1–50 位字母、数字或下划线。")
        keys.add(key)
        item = {"key": key, "title": _design_title(step.get("title")),
                "type": step.get("type", MissionType.TASK), "priority": step.get("priority", MissionPriority.P2)}
        if item["type"] not in MissionType.values or item["priority"] not in MissionPriority.values:
            raise ValidationFailure("步骤类型或优先级无效。")
        for field in ("content", "acceptance_criteria"):
            value = step.get(field, "")
            if not isinstance(value, str):
                raise ValidationFailure("步骤说明必须是 Markdown 文本。")
            for target in iter_references(value):
                try:
                    target_path = urlsplit(target).path
                except ValueError:
                    raise ValidationFailure("步骤中有不合法的链接。")
                if target_path.startswith(LIBRARY_PATH_PREFIX):
                    raise ValidationFailure("生产模板不能引用私人素材，请使用 http(s) 外链。", field_errors={"steps": ["不能引用私人素材。"]})
                if not target or target.startswith("#"):
                    continue
                _validate_http_url(target, "steps")
            item[field] = value
        tags = step.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(t, str) or not t.strip() or len(t.strip()) > 50 for t in tags):
            raise ValidationFailure("步骤标签须为非空字符串，每项最多 50 字符。")
        item["tags"] = list(dict.fromkeys(t.strip() for t in tags))
        prerequisites = step.get("prerequisite_keys", [])
        if not isinstance(prerequisites, list) or any(not isinstance(k, str) for k in prerequisites) or len(set(prerequisites)) != len(prerequisites):
            raise ValidationFailure("前置步骤须为不重复的 key 列表。")
        item["prerequisite_keys"] = prerequisites[:]
        normalized.append(item)
    adjacency = {key: set() for key in keys}
    for item in normalized:
        for prerequisite in item["prerequisite_keys"]:
            if prerequisite not in keys:
                raise ValidationFailure("前置步骤 key 不存在。")
            if prerequisite == item["key"] or _reaches(adjacency, item["key"], prerequisite):
                raise ValidationFailure("生产步骤不能自依赖或形成循环。")
            adjacency[prerequisite].add(item["key"])
    return normalized


def template_allowed_actions(actor, template):
    if not actor or not actor.is_active or (actor.pk != template.created_by_id and not _is_admin(actor)):
        return []
    return ["restore"] if template.archived else ["edit", "archive"]


@transaction.atomic
def create_production_template(*, actor, name, steps, description=""):
    if not _is_active_member(actor):
        raise PermissionDenied("只有有效成员可创建模板。")
    template = ProductionTemplate.objects.create(name=_design_title(name), description=description,
        steps=_validate_template_steps(steps), created_by=actor)
    ProductionTemplateEvent.objects.create(template=template, actor=actor, action="created")
    return template


@transaction.atomic
def update_production_template(*, actor, template_id, expected_version, changes):
    _acquire_team_lock()
    try:
        template = ProductionTemplate.objects.select_for_update().get(pk=template_id)
    except ProductionTemplate.DoesNotExist:
        raise NotFound("生产模板不存在。")
    if not template_allowed_actions(actor, template):
        raise PermissionDenied("只有模板创建者或管理员可以修改。")
    _check_version(template, expected_version)
    if set(changes) - {"name", "description", "steps", "archived"}:
        raise ValidationFailure("包含不支持的模板字段。")
    if template.archived and changes != {"archived": False}:
        raise ConflictError("请先恢复模板再编辑。", code="template_archived")
    if "archived" in changes and not isinstance(changes["archived"], bool):
        raise ValidationFailure("归档状态必须是布尔值。")
    before = {"name": template.name, "description": template.description, "steps": template.steps, "archived": template.archived}
    if "name" in changes:
        template.name = _design_title(changes["name"])
    if "description" in changes:
        template.description = changes["description"]
    if "steps" in changes:
        template.steps = _validate_template_steps(changes["steps"])
    if "archived" in changes:
        template.archived = changes["archived"]
    template.version += 1
    template.save()
    after = {"name": template.name, "description": template.description, "steps": template.steps, "archived": template.archived}
    action = ("archived" if template.archived else "restored") if before["archived"] != template.archived else "updated"
    ProductionTemplateEvent.objects.create(template=template, actor=actor, action=action, payload={"from": before, "to": after, "version": template.version})
    return template


@transaction.atomic
def instantiate_production(*, actor, element_id, expected_version, template_id, template_version, milestone_id=None):
    from copy import deepcopy

    _acquire_team_lock()
    try:
        asset = DesignElement.objects.select_for_update().get(pk=element_id)
        template = ProductionTemplate.objects.select_for_update().get(pk=template_id)
    except (DesignElement.DoesNotExist, ProductionTemplate.DoesNotExist):
        raise NotFound("资产或生产模板不存在。")
    if not design_allowed_actions(actor, asset):
        raise PermissionDenied("只有资产创建者或管理员可以生成任务。")
    if ProductionBatch.objects.filter(asset=asset).exists():
        raise ConflictError("该资产已生成生产任务。", code="production_already_generated")
    _check_version(asset, expected_version)
    _check_version(template, template_version)
    if asset.kind != DesignElement.Kind.ASSET:
        raise ValidationFailure("只有资产条目可以生成生产任务。")
    if asset.archived or template.archived:
        raise ConflictError("资产或模板已归档，不能生成任务。", code="production_archived")
    _resolve_milestone(milestone_id, require_accepting=True)
    steps = _validate_template_steps(template.steps)
    titles = {step["key"]: _design_title(f'{asset.title} · {step["title"]}') for step in steps}
    batch = ProductionBatch.objects.create(asset=asset, template=template, template_version=template.version,
        template_snapshot={"name": template.name, "steps": deepcopy(steps)}, created_by=actor)
    missions = {}
    for step in steps:
        mission = create_mission(actor=actor, title=titles[step["key"]], content=step["content"],
            acceptance_criteria=step["acceptance_criteria"], tags=step["tags"], type=step["type"],
            priority=step["priority"], asset_ids=[asset.pk], milestone_id=milestone_id)
        missions[step["key"]] = mission
        ProductionBatchItem.objects.create(batch=batch, step_key=step["key"], mission=mission)
    for step in steps:
        mission = missions[step["key"]]
        for key in step["prerequisite_keys"]:
            add_dependency(actor=actor, mission_id=mission.pk, prerequisite_id=missions[key].pk, expected_version=mission.version)
            mission.refresh_from_db(fields=["version"])
    asset.version += 1
    asset.save(update_fields=["version", "updated_at"])
    DesignElementEvent.objects.create(element=asset, actor=actor, action="instantiated", payload={"batch_id": str(batch.pk), "template_id": str(template.pk), "template_version": template.version, "mission_count": len(missions)})
    return batch


# 计划日期校验结束顺序并派生风险，保留原认领与实际完成规则。
def _validate_schedule(start, end):
    from datetime import date, datetime
    def parse(value):
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() == value:
                    return parsed
            except ValueError:
                pass
        raise ValidationFailure("计划日期必须是 YYYY-MM-DD 或 null。")
    start, end = parse(start), parse(end)
    if start and end and start > end:
        raise ValidationFailure("计划开始日期不能晚于结束日期。", field_errors={"planned_end_date": ["不能早于开始日期。"]})
    return start, end


def _schedule_values(mission):
    return {key: getattr(mission, key).isoformat() if getattr(mission, key) else None for key in ("planned_start_date", "planned_end_date")}


def schedule_risks_bulk(missions, *, today=None):
    missions = list(missions)
    by_id = {mission.pk: mission for mission in missions}
    conflicts = {pk: [] for pk in by_id}
    for mission_id, prerequisite_id, end in MissionDependency.objects.filter(mission_id__in=by_id).values_list("mission_id", "prerequisite_id", "prerequisite__planned_end_date"):
        start = by_id[mission_id].planned_start_date
        if start and end and end > start:
            conflicts[mission_id].append(str(prerequisite_id))
    today = today or timezone.localdate()
    return {m.pk: {
        "overdue": bool(m.status in [MissionStatus.OPEN, MissionStatus.IN_PROGRESS, MissionStatus.SUBMITTED] and m.planned_end_date and m.planned_end_date < today),
        "dependency_date_conflict_ids": sorted(conflicts[m.pk]),
        "beyond_milestone_due": bool(m.planned_end_date and m.milestone_id and m.milestone.due_date and m.planned_end_date > m.milestone.due_date),
    } for m in missions}



def _assert_schedule_dependencies(mission):
    if not mission.planned_end_date:
        return
    invalid_upstream = MissionDependency.objects.filter(mission=mission, prerequisite__planned_end_date__gt=mission.planned_end_date)
    invalid_downstream = MissionDependency.objects.filter(prerequisite=mission, mission__planned_end_date__lt=mission.planned_end_date)
    if invalid_upstream.exists() or invalid_downstream.exists():
        raise ConflictError("计划结束日期与依赖顺序冲突：任务不得早于任何前置结束；延后前置时请先调整下游日期。", code="schedule_dependency_conflict")


def bulk_update_missions(*, actor, payload):
    """整体验证输入后逐项独立提交，绝不为整批包外层事务。"""
    import uuid
    from common.exceptions import DomainError
    if not isinstance(payload, dict) or set(payload) != {'items', 'changes'}:
        raise ValidationFailure('必须且只能包含 items 和 changes。')
    items, changes = payload['items'], payload['changes']
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise ValidationFailure('一次须选择 1–50 个任务。')
    allowed = {'priority', 'milestone', 'planned_start_date', 'planned_end_date'}
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise ValidationFailure('只能批量修改优先级、里程碑与计划日期，且至少选择一个字段。')
    normalized, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'id', 'expected_version'}:
            raise ValidationFailure('每项须包含任务 id 和 expected_version。')
        try:
            pk = uuid.UUID(str(item['id']))
        except (ValueError, TypeError, AttributeError):
            raise ValidationFailure('任务 ID 必须为 UUID。')
        version = item['expected_version']
        if pk in seen or type(version) is not int or version < 1:
            raise ValidationFailure('任务不可重复，版本须为正整数。')
        normalized.append((pk, version)); seen.add(pk)
    changes = changes.copy()
    if 'priority' in changes and changes['priority'] not in MissionPriority.values:
        raise ValidationFailure('优先级无效。')
    if changes.get('milestone') is not None:
        try:
            changes['milestone'] = uuid.UUID(str(changes['milestone']))
        except (ValueError, TypeError, AttributeError):
            raise ValidationFailure('里程碑 ID 必须为 UUID 或 null。')
    for field in ('planned_start_date', 'planned_end_date'):
        if field in changes:
            changes[field] = _validate_schedule(changes[field], None)[0]
    if 'planned_start_date' in changes and 'planned_end_date' in changes:
        _validate_schedule(changes['planned_start_date'], changes['planned_end_date'])
    results = []
    for pk, version in normalized:
        try:
            mission = update_mission(actor=actor, mission_id=pk, expected_version=version, changes=changes)
            results.append({'id': str(pk), 'success': True, 'status': 200, 'mission': mission})
        except DomainError as exc:
            results.append({'id': str(pk), 'success': False, 'status': exc.status_code,
                'error': {'code': exc.code, 'message': exc.message, 'field_errors': exc.field_errors}})
    succeeded = sum(item['success'] for item in results)
    return {'results': results, 'succeeded_count': succeeded, 'failed_count': len(results) - succeeded}

# 委派写入口保持统一，具体实现独立成模块以隔离模型交接与任务状态机。
from .execution_services import (  # noqa: E402,F401
    create_execution, publish_execution_candidates, select_execution_candidates,
    upload_execution_candidate, complete_execution, cancel_execution, execution_reference,
)

from .code_services import (
    create_code_execution, stage_code_execution, publish_code_execution, cancel_code_execution,
)

# 交互只写有界交接记录，继续从统一业务服务入口调用。
def open_interaction(*args, **kwargs):
    from agent_bridge.interaction_services import open_interaction as implementation
    return implementation(*args, **kwargs)


def exchange_interaction(*args, **kwargs):
    from agent_bridge.interaction_services import exchange_interaction as implementation
    return implementation(*args, **kwargs)


def interaction_state(*args, **kwargs):
    from agent_bridge.interaction_services import interaction_state as implementation
    return implementation(*args, **kwargs)


def create_interaction_command(*args, **kwargs):
    from agent_bridge.interaction_services import create_interaction_command as implementation
    return implementation(*args, **kwargs)
