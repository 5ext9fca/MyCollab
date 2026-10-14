/**
 * DTO adapter between the read-only workspace API and Vue Flow (F5).
 *
 * The backend DTO stays the single source of truth: this module only renames
 * fields and adds presentation flags (selected/dimmed/markers). It never turns
 * `node.data` into an authorization signal — the backend still decides every
 * action.
 */
import { MarkerType } from '@vue-flow/core'
import type { Edge, Node, XYPosition } from '@vue-flow/core'

import type { WorkspaceEdge, WorkspaceNode, WorkspaceParentEdge } from '../api/types'
import { milestoneColor } from './milestoneColor'

export const MISSION_NODE_TYPE = 'mission'
export const NODE_WIDTH = 240
export const NODE_HEIGHT = 96

export interface MissionNodeData {
  node: WorkspaceNode
  selected: boolean
  dimmed: boolean
  /** Stable swatch derived from the mission's milestone id. */
  color: string
}

export interface MissionEdgeData {
  edge: WorkspaceEdge
  highlighted: boolean
  dimmed: boolean
  satisfied: boolean
}

export interface ParentEdgeData {
  parentId: string
  childId: string
}

export type PositionLookup = Map<string, XYPosition>

/** Build the Vue Flow nodes; positions come from the Dagre layout. */
export function buildMissionNodes(
  nodes: WorkspaceNode[],
  positions: PositionLookup,
  emphasis: Set<string> | null,
  selectedId: string | null,
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

/** Build the optional decomposition edges; never mixed with dependency styling. */
export function buildParentEdges(parentEdges: WorkspaceParentEdge[]): Edge<ParentEdgeData>[] {
  return parentEdges.map((edge) => ({
    id: `parent-${edge.parent_id}-${edge.child_id}`,
    source: edge.parent_id,
    target: edge.child_id,
    type: 'smoothstep',
    class: 'ws-edge ws-edge--parent',
    label: '拆分',
    data: { parentId: edge.parent_id, childId: edge.child_id },
  }))
}
