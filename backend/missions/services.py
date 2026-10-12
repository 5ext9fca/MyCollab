"""Single entry point for every business write.

Views, admin actions and future clients must go through these functions. Each
function takes the actor explicitly and re-checks permissions, the current
status and data constraints inside a transaction, so an operation can never be
performed by patching a field directly.
"""

from __future__ import annotations

from typing import Iterable

from django.db import transaction

from library.references import assert_markdown_references_allowed

from .exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from .models import (
    Comment,
    Mission,
    MissionEvent,
    MissionEventAction,
    MissionStatus,
    Tag,
)

_UNSET = object()
FROZEN_STATUSES = {MissionStatus.SUBMITTED, MissionStatus.DONE}


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


def _record_event(mission: Mission, actor, action: str, payload: dict | None = None) -> None:
    MissionEvent.objects.create(mission=mission, actor=actor, action=action, payload=payload or {})


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


def _would_create_cycle(child_id, parent: Mission) -> bool:
    """Return True if making ``parent`` the parent of ``child`` forms a cycle."""
    node = parent
    seen: set = set()
    while node is not None:
        if node.id == child_id:
            return True
        if node.id in seen:
            break
        seen.add(node.id)
        node = node.parent
    return False


def _assert_can_add_child(actor, parent: Mission) -> None:
    if parent.status in FROZEN_STATUSES or parent.status == MissionStatus.CANCELLED:
        raise ConflictError("已完成或已取消的任务不能新增子任务。", code="parent_not_open")
    if actor.pk not in {parent.creator_id, parent.assignee_id}:
        raise PermissionDenied("只有任务的发起者或认领者可以新增子任务。")


def allowed_actions(user, mission: Mission) -> list[str]:
    """Server-computed capabilities the frontend uses to show buttons."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    is_creator = mission.creator_id == user.pk
    is_assignee = mission.assignee_id == user.pk
    actions: list[str] = []
    if mission.status == MissionStatus.OPEN and mission.assignee_id is None:
        actions.append("claim")
    if is_assignee and mission.status == MissionStatus.IN_PROGRESS:
        actions.extend(["release", "submit"])
    if is_creator and mission.status == MissionStatus.SUBMITTED:
        actions.append("review")
    if is_creator and mission.status in (MissionStatus.OPEN, MissionStatus.IN_PROGRESS):
        actions.extend(["edit", "cancel"])
    if (is_creator or is_assignee) and mission.status not in (
        MissionStatus.DONE,
        MissionStatus.CANCELLED,
    ):
        actions.append("create_child")
    return actions


# --------------------------------------------------------------------------- #
# Commands
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
) -> Mission:
    title = (title or "").strip()
    if not title:
        raise ValidationFailure("标题不能为空。", field_errors={"title": ["标题不能为空。"]})

    content = content or ""
    acceptance_criteria = acceptance_criteria or ""
    assert_markdown_references_allowed(content, actor, field="content")
    assert_markdown_references_allowed(acceptance_criteria, actor, field="acceptance_criteria")

    parent = None
    if parent_id is not None:
        parent = _get_locked(parent_id)
        _assert_can_add_child(actor, parent)

    mission = Mission.objects.create(
        title=title,
        content=content,
        acceptance_criteria=acceptance_criteria,
        creator=actor,
        parent=parent,
        status=MissionStatus.OPEN,
    )
    _apply_tags(mission, tags)
    _record_event(
        mission,
        actor,
        MissionEventAction.CREATED,
        {"parent_id": str(parent.id) if parent else None},
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
def update_mission(*, actor, mission_id, version: int, changes: dict) -> Mission:
    mission = _get_locked(mission_id)
    if mission.creator_id != actor.pk:
        raise PermissionDenied("只有发起者可以修改任务目标与验收标准。")
    if mission.version != version:
        raise ConflictError("任务已被他人修改，请刷新后重试。", code="version_conflict")
    if mission.status not in (MissionStatus.OPEN, MissionStatus.IN_PROGRESS):
        raise ConflictError("当前状态已冻结内容，请先退回进行中再修改。", code="mission_frozen")

    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise ValidationFailure("标题不能为空。", field_errors={"title": ["标题不能为空。"]})
        mission.title = title
    if "content" in changes:
        content = changes["content"] or ""
        assert_markdown_references_allowed(content, actor, field="content")
        mission.content = content
    if "acceptance_criteria" in changes:
        acceptance_criteria = changes["acceptance_criteria"] or ""
        assert_markdown_references_allowed(acceptance_criteria, actor, field="acceptance_criteria")
        mission.acceptance_criteria = acceptance_criteria
    if "parent" in changes:
        new_parent_id = changes["parent"]
        if new_parent_id is None:
            mission.parent = None
        else:
            new_parent = _get_locked(new_parent_id)
            if _would_create_cycle(mission.id, new_parent):
                raise ConflictError("不能把任务移动到自身或其子任务下。", code="parent_cycle")
            if new_parent.status in FROZEN_STATUSES or new_parent.status == MissionStatus.CANCELLED:
                raise ConflictError("不能挂到已完成或已取消的任务下。", code="parent_not_open")
            if actor.pk not in {new_parent.creator_id, new_parent.assignee_id}:
                raise PermissionDenied("只有目标父任务的发起者或认领者可以建立该父子关系。")
            mission.parent = new_parent
    if "tags" in changes:
        _apply_tags(mission, changes["tags"])

    mission.version += 1
    mission.save()
    _record_event(mission, actor, MissionEventAction.UPDATED, {"version": mission.version})
    return mission


@transaction.atomic
def claim_mission(*, actor, mission_id) -> Mission:
    mission = _get_locked(mission_id)
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
def release_mission(*, actor, mission_id) -> Mission:
    mission = _get_locked(mission_id)
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


@transaction.atomic
def submit_mission(*, actor, mission_id, result: str) -> Mission:
    mission = _get_locked(mission_id)
    if mission.assignee_id != actor.pk:
        raise PermissionDenied("只有认领者可以提交成果。")
    if mission.status != MissionStatus.IN_PROGRESS:
        raise ConflictError("只有进行中的任务可以提交。", code="submit_conflict")

    result = (result or "").strip()
    if not result:
        raise ValidationFailure("提交成果不能为空。", field_errors={"result": ["提交成果不能为空。"]})
    assert_markdown_references_allowed(result, actor, field="result")

    if mission.children.exclude(status__in=[MissionStatus.DONE, MissionStatus.CANCELLED]).exists():
        raise ConflictError("仍有未完成的子任务，无法提交父任务。", code="children_incomplete")

    mission.result = result
    mission.status = MissionStatus.SUBMITTED
    mission.version += 1
    mission.save(update_fields=["result", "status", "version", "updated_at"])
    _record_event(mission, actor, MissionEventAction.SUBMITTED)
    return mission


@transaction.atomic
def review_mission(*, actor, mission_id, approve: bool, comment: str = "") -> Mission:
    mission = _get_locked(mission_id)
    if mission.creator_id != actor.pk:
        raise PermissionDenied("只有发起者可以验收或退回。")
    if mission.status != MissionStatus.SUBMITTED:
        raise ConflictError("任务未处于待验收状态。", code="review_conflict")

    mission.status = MissionStatus.DONE if approve else MissionStatus.IN_PROGRESS
    mission.version += 1
    mission.save(update_fields=["status", "version", "updated_at"])
    _record_event(
        mission,
        actor,
        MissionEventAction.REVIEW_APPROVED if approve else MissionEventAction.REVIEW_REJECTED,
        {"comment": comment or ""},
    )
    return mission


@transaction.atomic
def cancel_mission(*, actor, mission_id, reason: str = "") -> Mission:
    mission = _get_locked(mission_id)
    if mission.creator_id != actor.pk:
        raise PermissionDenied("只有发起者可以取消任务。")
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
# Comments
# --------------------------------------------------------------------------- #
@transaction.atomic
def create_comment(*, actor, mission_id, content: str = "") -> Comment:
    """Any team member may comment on any mission, in any status."""
    mission = _get_mission(mission_id)
    content = content or ""
    assert_markdown_references_allowed(content, actor, field="content")
    return Comment.objects.create(mission=mission, author=actor, content=content)


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
