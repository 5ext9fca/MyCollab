/**
 * Dependency-free layered DAG layout for the F5 dependency graph.
 *
 * The canvas x axis is the dependency layer (left = earlier prerequisites),
 * never time, status or priority (NEW_FUNCTION.md 10.5). Nodes with no edges
 * still get a position so isolated missions stay visible.
 */
import type { WorkspaceEdge, WorkspaceNode, WorkspaceParentEdge } from './api/types'

export const NODE_WIDTH = 220
export const NODE_HEIGHT = 92
export const GAP_X = 130
export const GAP_Y = 28

const PRIORITY_ORDER: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3 }

export interface PositionedNode {
  node: WorkspaceNode
  x: number
  y: number
  layer: number
}

export interface EdgeGeometry<E> {
  edge: E
  path: string
  from: PositionedNode | undefined
  to: PositionedNode | undefined
}

export interface GraphLayout {
  nodes: PositionedNode[]
  positions: Map<string, PositionedNode>
  dependencyEdges: EdgeGeometry<WorkspaceEdge>[]
  parentEdges: EdgeGeometry<WorkspaceParentEdge>[]
  width: number
  height: number
}

function sortKey(node: WorkspaceNode): [number, string, string] {
  return [PRIORITY_ORDER[node.priority] ?? 9, node.created_at ?? '', node.id]
}

function curve(from: PositionedNode, to: PositionedNode): string {
  const x1 = from.x + NODE_WIDTH
  const y1 = from.y + NODE_HEIGHT / 2
  const x2 = to.x
  const y2 = to.y + NODE_HEIGHT / 2
  if (x2 >= x1) {
    const mid = x1 + (x2 - x1) / 2
    return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`
  }
  // Back edge (only possible around a cycle): bow below to stay readable.
  const dip = Math.max(from.y, to.y) + NODE_HEIGHT + 24
  return `M ${x1} ${y1} C ${x1 + 60} ${dip}, ${x2 - 60} ${dip}, ${x2} ${y2}`
}

/** Longest-path layering; nodes caught in a cycle fall back to layer 0. */
export function assignLayers(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
): Map<string, number> {
  const ids = new Set(nodes.map((node) => node.id))
  const prereqs = new Map<string, string[]>()
  const dependents = new Map<string, string[]>()
  for (const node of nodes) {
    prereqs.set(node.id, [])
    dependents.set(node.id, [])
  }
  for (const edge of edges) {
    if (!ids.has(edge.mission_id) || !ids.has(edge.prerequisite_id)) continue
    prereqs.get(edge.mission_id)!.push(edge.prerequisite_id)
    dependents.get(edge.prerequisite_id)!.push(edge.mission_id)
  }

  const layer = new Map<string, number>()
  const indegree = new Map<string, number>()
  const queue: string[] = []
  for (const node of nodes) {
    indegree.set(node.id, prereqs.get(node.id)!.length)
    if (indegree.get(node.id) === 0) {
      layer.set(node.id, 0)
      queue.push(node.id)
    }
  }
  while (queue.length) {
    const id = queue.shift()!
    for (const dependent of dependents.get(id)!) {
      layer.set(dependent, Math.max(layer.get(dependent) ?? 0, (layer.get(id) ?? 0) + 1))
      indegree.set(dependent, (indegree.get(dependent) ?? 1) - 1)
      if (indegree.get(dependent) === 0) queue.push(dependent)
    }
  }
  for (const node of nodes) {
    if (!layer.has(node.id)) layer.set(node.id, 0)
  }
  return layer
}

export function layoutGraph(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
  parentEdges: WorkspaceParentEdge[] = [],
): GraphLayout {
  const layer = assignLayers(nodes, edges)
  const buckets = new Map<number, WorkspaceNode[]>()
  for (const node of nodes) {
    const depth = layer.get(node.id) ?? 0
    if (!buckets.has(depth)) buckets.set(depth, [])
    buckets.get(depth)!.push(node)
  }
  for (const bucket of buckets.values()) bucket.sort((a, b) => compare(sortKey(a), sortKey(b)))

  const heights = new Map<number, number>()
  for (const [depth, bucket] of buckets) {
    heights.set(depth, bucket.length * NODE_HEIGHT + Math.max(0, bucket.length - 1) * GAP_Y)
  }
  const tallest = Math.max(0, ...heights.values())

  const positioned: PositionedNode[] = []
  const positions = new Map<string, PositionedNode>()
  for (const [depth, bucket] of [...buckets.entries()].sort((a, b) => a[0] - b[0])) {
    const layerHeight = heights.get(depth) ?? 0
    const offsetY = (tallest - layerHeight) / 2
    bucket.forEach((node, index) => {
      const item: PositionedNode = {
        node,
        layer: depth,
        x: depth * (NODE_WIDTH + GAP_X),
        y: offsetY + index * (NODE_HEIGHT + GAP_Y),
      }
      positioned.push(item)
      positions.set(node.id, item)
    })
  }

  const dependencyEdges = edges.map((edge) => {
    const from = positions.get(edge.prerequisite_id)
    const to = positions.get(edge.mission_id)
    return {
      edge,
      from,
      to,
      path: from && to ? curve(from, to) : '',
    }
  })
  const positionedParentEdges = parentEdges.map((edge) => {
    const from = positions.get(edge.parent_id)
    const to = positions.get(edge.child_id)
    return {
      edge,
      from,
      to,
      path: from && to ? curve(from, to) : '',
    }
  })

  const width = positioned.reduce((max, item) => Math.max(max, item.x + NODE_WIDTH), 0)
  const height = positioned.reduce((max, item) => Math.max(max, item.y + NODE_HEIGHT), 0)

  return {
    nodes: positioned,
    positions,
    dependencyEdges,
    parentEdges: positionedParentEdges,
    width,
    height,
  }
}

function compare(a: [number, string, string], b: [number, string, string]): number {
  if (a[0] !== b[0]) return a[0] - b[0]
  if (a[1] !== b[1]) return a[1] < b[1] ? -1 : 1
  return a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0
}

/** Direct prerequisites and dependents of a node, from the visible edges. */
export function directRelations(
  id: string,
  edges: WorkspaceEdge[],
): { prerequisites: Set<string>; dependents: Set<string> } {
  const prerequisites = new Set<string>()
  const dependents = new Set<string>()
  for (const edge of edges) {
    if (edge.mission_id === id) prerequisites.add(edge.prerequisite_id)
    if (edge.prerequisite_id === id) dependents.add(edge.mission_id)
  }
  return { prerequisites, dependents }
}
