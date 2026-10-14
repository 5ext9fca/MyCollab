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
export const NODE_WIDTH = 220
export const NODE_HEIGHT = 120
/** Vertical gap between the stacked cards of one parent/child family. */
export const GROUP_GAP = 12
/** Horizontal indent applied per nesting level inside a family. */
export const GROUP_INDENT = 16

/**
 * One vertical stack laid out by Dagre as a single node.
 *
 * When "显示父子任务关系" is off every node is its own group of one member; when
 * it is on, a family root plus its visible descendants form one group and the
 * cards are stacked in `memberIds` order.
 */
export interface LayoutGroup {
  /** Dagre node id: the family root (or the node itself when ungrouped). */
  id: string
  /** Visible members in vertical order, root first. */
  memberIds: string[]
  /** Nesting depth per member (0 = root). */
  depths: number[]
}

/** Parent/child presentation flags shared by the graph node components. */
export interface GroupInfo {
  /** Total descendants (whole subtree, including collapsed ones) per node. */
  descendantCount: Map<string, number>
  /** Nodes whose subtree is collapsed. */
  collapsed: Set<string>
  /** Nesting depth per visible node (0 = family root / ungrouped). */
  depth: Map<string, number>
  /** Dagre blocks, one per family root. */
  groups: LayoutGroup[]
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
 * Build the Vue Flow nodes; positions come from the Dagre layout and the
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
