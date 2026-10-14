"""Read-only workspace aggregations (F5).

Two GET-only endpoints feed the SPA workspace:

* ``/api/workspace/overview/`` — the "milestone x status" board, plus the
  page summary counts.
* ``/api/workspace/graph/`` — the dependency DAG (nodes + directed edges).

Both reuse the F1–F4 data, the shared mission filters and the server-computed
derived flags. They never write: every mutation still goes through
``missions/services.py``. The two views are deliberately separate from the
paginated ``/api/missions/`` list so a single page cannot masquerade as a
complete dependency graph (see NEW_FUNCTION.md section 10.9).
"""

from __future__ import annotations

import hashlib

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserBriefSerializer

from .filters import apply_mission_filters, parse_bool, parse_int, parse_uuid
from .models import (
    Milestone,
    MilestoneStatus,
    Mission,
    MissionDependency,
    MissionStatus,
)
from .permissions import IsTeamMember
from .services import allowed_actions, derived_state_bulk

#: Status columns of the overview board, in display order.
STATUS_COLUMNS = [
    MissionStatus.OPEN,
    MissionStatus.IN_PROGRESS,
    MissionStatus.SUBMITTED,
    MissionStatus.DONE,
    MissionStatus.CANCELLED,
]

STATUS_LABELS = {
    MissionStatus.OPEN: "待认领",
    MissionStatus.IN_PROGRESS: "进行中",
    MissionStatus.SUBMITTED: "待验收",
    MissionStatus.DONE: "已完成",
    MissionStatus.CANCELLED: "已取消",
}

#: Cards returned per group/status column before "load more".
OVERVIEW_COLUMN_LIMIT_DEFAULT = 20
OVERVIEW_COLUMN_LIMIT_MAX = 100

#: Graph safety budgets (NEW_FUNCTION.md 10.9): never silently drop edges.
GRAPH_NODE_LIMIT = 200
GRAPH_EDGE_LIMIT = 1000
GRAPH_CONTEXT_LIMIT = 50
GRAPH_MAX_DEPTH = 5

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_MILESTONE_STATUS_ORDER = {
    MilestoneStatus.ACTIVE: 0,
    MilestoneStatus.PLANNED: 1,
    MilestoneStatus.COMPLETED: 2,
    MilestoneStatus.CANCELLED: 3,
}

_FILTER_PARAMS = (
    "q",
    "search",
    "milestone",
    "status",
    "assignee",
    "reviewer",
    "creator",
    "type",
    "priority",
    "blocked",
    "revalidation",
    "tag",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _iso(value):
    return value.isoformat() if value else None


def _user_brief(user):
    if user is None:
        return None
    return UserBriefSerializer(user).data


def _mission_queryset():
    return Mission.objects.select_related(
        "creator", "assignee", "reviewer", "parent", "milestone"
    )


def _filters_active(params) -> bool:
    for name in _FILTER_PARAMS:
        if name == "tag":
            if params.getlist("tag"):
                return True
            continue
        value = params.get(name)
        if value is not None and str(value).strip():
            return True
    return False


def _node(mission: Mission, derived: dict, user, *, is_context: bool = False) -> dict:
    milestone = mission.milestone
    return {
        "id": str(mission.id),
        "title": mission.title,
        "type": mission.type,
        "priority": mission.priority,
        "status": mission.status,
        "creator": _user_brief(mission.creator),
        "assignee": _user_brief(mission.assignee),
        "reviewer": _user_brief(mission.reviewer),
        "parent_id": str(mission.parent_id) if mission.parent_id else None,
        "milestone_id": str(mission.milestone_id) if mission.milestone_id else None,
        "milestone_name": milestone.name if milestone else None,
        "version": mission.version,
        "created_at": _iso(mission.created_at),
        "updated_at": _iso(mission.updated_at),
        "is_blocked": derived["is_blocked"],
        "has_unresolved_prerequisites": derived["has_unresolved_prerequisites"],
        "requires_revalidation": derived["needs_dependency_review"],
        "needs_dependency_review": derived["needs_dependency_review"],
        "blocking_count": len(derived["blocking_mission_ids"]),
        "unfinished_child_count": len(derived["unfinished_child_ids"]),
        "reviewer_missing": derived["reviewer_missing"],
        "milestone_closed": derived["milestone_closed"],
        "is_context": is_context,
        "allowed_actions": allowed_actions(user, mission),
    }


def _board_sort_key(mission: Mission):
    return (
        _PRIORITY_ORDER.get(mission.priority, 9),
        mission.created_at,
        str(mission.id),
    )


def _milestone_sort_key(milestone: Milestone):
    return (
        _MILESTONE_STATUS_ORDER.get(milestone.status, 9),
        milestone.due_date is None,
        milestone.due_date or timezone.localdate(),
        str(milestone.id),
    )


def _milestone_brief(milestone: Milestone | None) -> dict | None:
    if milestone is None:
        return None
    overdue = (
        milestone.due_date is not None
        and milestone.status in (MilestoneStatus.PLANNED, MilestoneStatus.ACTIVE)
        and milestone.due_date < timezone.localdate()
    )
    return {
        "id": str(milestone.id),
        "name": milestone.name,
        "status": milestone.status,
        "due_date": _iso(milestone.due_date),
        "overdue": overdue,
    }


def _counts(missions) -> dict:
    """Effective/done counts; ``Cancelled`` never enters the denominator."""
    effective = [m for m in missions if m.status != MissionStatus.CANCELLED]
    done = [m for m in effective if m.status == MissionStatus.DONE]
    return {
        "total": len(missions),
        "effective_total": len(effective),
        "done": len(done),
        "progress": (len(done) / len(effective)) if effective else None,
    }


# --------------------------------------------------------------------------- #
# Read snapshot consistency
# --------------------------------------------------------------------------- #
def _mission_signature(mission: Mission) -> str:
    """Stable per-mission fingerprint: any write bumps ``version``/``updated_at``."""
    return f"{mission.id}:{mission.version}:{mission.status}:{mission.updated_at.isoformat()}"


def _revision(parts) -> str:
    """Deterministic revision id for the read snapshot.

    A fresh random ``snapshot_id`` per request cannot tell whether data changed
    (NEW_FUNCTION.md 11), so callers get a hash that only changes when the
    underlying rows do. Clients may compare it before merging pages.
    """
    digest = hashlib.sha1("\n".join(sorted(parts)).encode("utf-8"))
    return digest.hexdigest()[:16]


def _missions_revision(missions) -> str:
    return _revision(_mission_signature(mission) for mission in missions)



# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
class WorkspaceOverviewView(APIView):
    """Milestone x status board plus the page summary counts."""

    permission_classes = [IsTeamMember]

    def get(self, request):
        params = request.query_params
        user = request.user

        matched = list(apply_mission_filters(_mission_queryset(), params, user))
        matched_ids = {mission.id for mission in matched}
        derived = derived_state_bulk(matched)
        nodes = {
            mission.id: _node(mission, derived[mission.id], user) for mission in matched
        }

        column_limit = parse_int(
            params.get("column_limit"),
            "column_limit",
            default=OVERVIEW_COLUMN_LIMIT_DEFAULT,
            minimum=1,
            maximum=OVERVIEW_COLUMN_LIMIT_MAX,
        )

        # Full visible scope (filters change display, not the milestone totals).
        all_missions = list(_mission_queryset())
        by_milestone: dict = {}
        unassigned: list = []
        for mission in all_missions:
            if mission.milestone_id:
                by_milestone.setdefault(mission.milestone_id, []).append(mission)
            else:
                unassigned.append(mission)

        requested_milestone = (params.get("milestone") or "").strip()
        groups = []
        if requested_milestone in {"none", "null"}:
            milestones: list = []
            include_unassigned = True
        elif requested_milestone:
            milestones = list(
                Milestone.objects.filter(pk=parse_uuid(requested_milestone, "milestone"))
            )
            include_unassigned = False
        else:
            milestones = sorted(list(Milestone.objects.all()), key=_milestone_sort_key)
            # The "未归属里程碑" bucket is never omitted by default.
            include_unassigned = True

        for milestone in milestones:
            groups.append(
                self._group(
                    milestone, by_milestone.get(milestone.id, []), nodes, column_limit
                )
            )
        if include_unassigned:
            groups.append(self._group(None, unassigned, nodes, column_limit))

        summary = {
            "matched_total": len(matched),
            "effective_total": len(
                [m for m in matched if m.status != MissionStatus.CANCELLED]
            ),
            "done": len([m for m in matched if m.status == MissionStatus.DONE]),
            "blocked": len(
                [m for m in matched if derived[m.id]["is_blocked"]]
            ),
            "submitted": len(
                [m for m in matched if m.status == MissionStatus.SUBMITTED]
            ),
            "requires_revalidation": len(
                [m for m in matched if derived[m.id]["needs_dependency_review"]]
            ),
        }

        return Response(
            {
                "generated_at": _iso(timezone.now()),
                "revision": _missions_revision(all_missions),
                "filters_active": _filters_active(params),
                "column_limit": column_limit,
                "columns": STATUS_COLUMNS,
                "column_labels": STATUS_LABELS,
                "summary": summary,
                "groups": groups,
            }
        )

    @staticmethod
    def _group(milestone, group_missions, nodes, column_limit) -> dict:
        matched_nodes = sorted(
            [nodes[m.id] for m in group_missions if m.id in nodes],
            key=lambda node: (
                _PRIORITY_ORDER.get(node["priority"], 9),
                node["created_at"] or "",
                node["id"],
            ),
        )
        columns = {}
        matched_counts = {}
        loaded = {}
        for status in STATUS_COLUMNS:
            items = [node for node in matched_nodes if node["status"] == status]
            matched_counts[status] = len(items)
            columns[status] = items[:column_limit]
            loaded[status] = len(columns[status])

        return {
            "milestone": _milestone_brief(milestone),
            "is_unassigned": milestone is None,
            "full_counts": _counts(group_missions),
            "full_counts_scope": "milestone_all_visible",
            "matched_counts": matched_counts,
            "matched_counts_scope": "active_filters",
            "matched_total": sum(matched_counts.values()),
            "loaded": loaded,
            "columns": columns,
        }


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
def _neighbor_ids(ids, direction: str) -> set:
    ids = list(ids)
    if not ids:
        return set()
    neighbors: set = set()
    if direction in ("upstream", "both"):
        neighbors |= set(
            MissionDependency.objects.filter(mission_id__in=ids).values_list(
                "prerequisite_id", flat=True
            )
        )
    if direction in ("downstream", "both"):
        neighbors |= set(
            MissionDependency.objects.filter(prerequisite_id__in=ids).values_list(
                "mission_id", flat=True
            )
        )
    return neighbors


class WorkspaceGraphView(APIView):
    """Dependency DAG: nodes are missions, explicit dependencies are edges."""

    permission_classes = [IsTeamMember]

    def get(self, request):
        params = request.query_params
        user = request.user

        scope = (params.get("scope") or "team").strip().lower()
        if scope not in {"team", "milestone", "mission"}:
            scope = "team"
        expand = (params.get("expand") or "one").strip().lower()
        if expand not in {"none", "one", "all"}:
            expand = "one"
        direction = (params.get("direction") or "both").strip().lower()
        if direction not in {"upstream", "downstream", "both"}:
            direction = "both"
        depth = parse_int(
            params.get("depth"),
            "depth",
            default=1,
            minimum=1,
            maximum=GRAPH_MAX_DEPTH,
        )
        context_param = params.get("context")
        include_context = True if context_param is None else parse_bool(context_param)
        include_parent = parse_bool(params.get("include_parent") or "")

        matched = list(apply_mission_filters(_mission_queryset(), params, user))
        matched_ids = {mission.id for mission in matched}

        focus = None
        focus_raw = (params.get("focus") or "").strip()
        if focus_raw:
            focus = _mission_queryset().filter(pk=parse_uuid(focus_raw, "focus")).first()

        nodes: dict = {}
        context_ids: set = set()
        nodes_truncated = False
        context_truncated = False

        if scope == "mission" and focus is not None:
            nodes[focus.id] = focus
        else:
            for mission in matched:
                nodes[mission.id] = mission

        # Explicit transitive expansion around the selected mission
        # ("全部上游/下游"). Marked as context when it falls outside the filter.
        if focus is not None and expand != "none" and focus.id in nodes:
            max_depth = depth if expand == "all" else 1
            frontier = {focus.id}
            for _ in range(max_depth):
                if not frontier:
                    break
                neighbor_ids = _neighbor_ids(frontier, direction) - set(nodes.keys())
                if not neighbor_ids:
                    break
                budget = GRAPH_NODE_LIMIT - len(nodes)
                if budget <= 0:
                    nodes_truncated = True
                    break
                if len(neighbor_ids) > budget:
                    nodes_truncated = True
                fetched = _fetch(list(neighbor_ids)[:budget])
                for mid, mission in fetched.items():
                    nodes[mid] = mission
                    if mid not in matched_ids:
                        context_ids.add(mid)
                frontier = set(fetched.keys())

        # Default one-hop context so a filter can never make a mission look
        # dependency-free when it is not.
        if include_context and scope != "mission":
            neighbor_ids = _neighbor_ids(set(nodes.keys()), "both") - set(nodes.keys())
            node_budget = GRAPH_NODE_LIMIT - len(nodes)
            context_budget = min(GRAPH_CONTEXT_LIMIT, max(0, node_budget))
            if neighbor_ids and len(neighbor_ids) > context_budget:
                if context_budget == GRAPH_CONTEXT_LIMIT:
                    context_truncated = True
                else:
                    nodes_truncated = True
            fetched = _fetch(sorted(neighbor_ids)[:context_budget]) if context_budget > 0 else {}
            for mid, mission in fetched.items():
                nodes[mid] = mission
                if mid not in matched_ids:
                    context_ids.add(mid)

        node_ids = list(nodes.keys())
        dependency_rows = list(
            MissionDependency.objects.filter(
                mission_id__in=node_ids, prerequisite_id__in=node_ids
            )
            .order_by("created_at", "id")
            .values_list("id", "mission_id", "prerequisite_id")
        )
        edges = []
        for edge_id, mission_id, prerequisite_id in dependency_rows:
            edges.append(
                {
                    "id": str(edge_id),
                    "mission_id": str(mission_id),
                    "prerequisite_id": str(prerequisite_id),
                    "is_satisfied": nodes[prerequisite_id].status == MissionStatus.DONE,
                    "cross_milestone": nodes[prerequisite_id].milestone_id
                    != nodes[mission_id].milestone_id,
                }
            )
        edges_truncated = len(edges) > GRAPH_EDGE_LIMIT
        edges = edges[:GRAPH_EDGE_LIMIT]

        parent_edges = []
        if include_parent:
            for mission in nodes.values():
                if mission.parent_id and mission.parent_id in nodes:
                    parent_edges.append(
                        {
                            "child_id": str(mission.id),
                            "parent_id": str(mission.parent_id),
                        }
                    )
            parent_edges.sort(key=lambda edge: (edge["parent_id"], edge["child_id"]))

        missions = list(nodes.values())
        derived = derived_state_bulk(missions)
        node_payload = [
            _node(
                mission,
                derived[mission.id],
                user,
                is_context=mission.id in context_ids,
            )
            for mission in sorted(missions, key=_board_sort_key)
        ]

        truncation_reasons = []
        if nodes_truncated:
            truncation_reasons.append("node_limit")
        if context_truncated:
            truncation_reasons.append("context_limit")
        if edges_truncated:
            truncation_reasons.append("edge_limit")
        truncated = bool(truncation_reasons)

        revision = _revision(
            [
                *(_mission_signature(mission) for mission in missions),
                *(
                    f"e:{edge['id']}:{edge['prerequisite_id']}:{edge['mission_id']}"
                    for edge in edges
                ),
                *(
                    f"p:{edge['parent_id']}:{edge['child_id']}" for edge in parent_edges
                ),
            ]
        )

        return Response(
            {
                "generated_at": _iso(timezone.now()),
                "revision": revision,
                "filters_active": _filters_active(params),
                "nodes": node_payload,
                "edges": edges,
                "parent_edges": parent_edges,
                "meta": {
                    "scope": scope,
                    "focus": str(focus.id) if focus else None,
                    "expand": expand,
                    "direction": direction,
                    "depth": depth,
                    "matched_count": len(matched_ids),
                    "matched_included": len(matched_ids & set(nodes.keys())),
                    "context_count": len(context_ids),
                    "node_count": len(node_payload),
                    "edge_count": len(edges),
                    "parent_edge_count": len(parent_edges),
                    "node_limit": GRAPH_NODE_LIMIT,
                    "edge_limit": GRAPH_EDGE_LIMIT,
                    "context_limit": GRAPH_CONTEXT_LIMIT,
                    "nodes_truncated": nodes_truncated,
                    "context_truncated": context_truncated,
                    "edges_truncated": edges_truncated,
                    "truncated": truncated,
                    "truncation_reasons": truncation_reasons,
                    "relationships_complete": not truncated,
                },
            }
        )


def _fetch(ids) -> dict:
    if not ids:
        return {}
    return {mission.id: mission for mission in _mission_queryset().filter(pk__in=ids)}


__all__ = [
    "GRAPH_EDGE_LIMIT",
    "GRAPH_NODE_LIMIT",
    "WorkspaceGraphView",
    "WorkspaceOverviewView",
]
