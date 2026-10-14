/**
 * DTO adapter between the read-only workspace API and Vue Flow (F5).
 *
 * The backend DTO stays the single source of truth: this module only renames
 * fields and adds presentation flags (selected/dimmed/markers, parent/child
 * grouping). It never turns `node.data` into an authorization signal — the
 * backend still decides every action.
 */
import { MarkerType } from '@vue-flow/core'
import type { Edge, Node, XYPosition } from '@vue-flow/core'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import { milestoneColor } from './milestoneColor'

export const MISSION_NODE_TYPE = 'mission'
/** Card width in CSS pixels; the layout uses it as the column pitch unit. */
export const NODE_WIDTH = 220
/** Card height in CSS pixels; the graph card is fixed to this height. */
export const NODE_HEIGHT = 120

/**
 * Handle ids. The graph now reads top to bottom, so a prerequisite leaves its
 * card from the bottom and a dependent enters from the top. The page never
 * creates connections, so these are only routing anchors.
 */
export const DEPENDENCY_SOURCE_HANDLE = 'dep-source'
export const DEPENDENCY_TARGET_HANDLE = 'dep-target'

/** Parent/child presentation flags shared by the graph node components. */
export interface GroupInfo {
  /** Total descendants (whole subtree, collapsed ones included) per node. */
  descendantCount: Map<string, number>
  /** Nodes whose subtree is collapsed. */
  collapsed: Set<string>
  /** Nesting depth per visible node (0 = family root / ungrouped). */
  depth: Map<string, number>
  /** Visible parent -> visible children, in display order. */
  childrenOf: Map<string, string[]>
}

export interface MissionNodeData {
  node: WorkspaceNode
  selected: boolean
  dimmed: boolean
  /** Stable swatch derived from the mission's milestone id. */
  color: string
  /** Nesting depth inside its family (0 when ungrouped). */
  depth: number
  /** Total descendants of this node, collapsed ones included. */
  descendantCount: number
  /** True when this node's subtree is collapsed. */
  collapsed: boolean
}

export interface MissionEdgeData {
  edge: WorkspaceEdge
  highlighted: boolean
  dimmed: boolean
  satisfied: boolean
}

export type PositionLookup = Map<string, XYPosition>

/**
 * Build the Vue Flow nodes; positions come from the layered layout and the
 * optional grouping only adds presentation flags.
 */
export function buildMissionNodes(
  nodes: WorkspaceNode[],
  positions: PositionLookup,
  emphasis: Set<string> | null,
  selectedId: string | null,
  grouping: GroupInfo | null = null,
): Node<MissionNodeData>[] {
  return nodes.map((node) => ({
    id: node.id,
    type: MISSION_NODE_TYPE,
    position: positions.get(node.id) ?? { x: 0, y: 0 },
    draggable: false,
    connectable: false,
    data: {
      node,
      selected: node.id === selectedId,
      dimmed: emphasis ? !emphasis.has(node.id) : false,
      color: milestoneColor(node.milestone_id),
      depth: grouping?.depth.get(node.id) ?? 0,
      descendantCount: grouping?.descendantCount.get(node.id) ?? 0,
      collapsed: grouping?.collapsed.has(node.id) ?? false,
    },
  }))
}

/** Build the dependency edges (prerequisite -> mission) with arrow + state. */
export function buildDependencyEdges(
  edges: WorkspaceEdge[],
  selectedId: string | null,
): Edge<MissionEdgeData>[] {
  return edges.map((edge) => {
    const highlighted =
      !!selectedId && (edge.mission_id === selectedId || edge.prerequisite_id === selectedId)
    const classes = ['ws-edge', edge.is_satisfied ? 'ws-edge--satisfied' : 'ws-edge--pending']
    if (highlighted) classes.push('ws-edge--highlight')
    else if (selectedId) classes.push('ws-edge--dim')
    return {
      id: edge.id,
      source: edge.prerequisite_id,
      target: edge.mission_id,
      sourceHandle: DEPENDENCY_SOURCE_HANDLE,
      targetHandle: DEPENDENCY_TARGET_HANDLE,
      type: 'smoothstep',
      markerEnd: MarkerType.ArrowClosed,
      class: classes.join(' '),
      data: {
        edge,
        highlighted,
        dimmed: !!selectedId && !highlighted,
        satisfied: edge.is_satisfied,
      },
    }
  })
}
