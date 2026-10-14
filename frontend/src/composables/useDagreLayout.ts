/**
 * Dagre layout for the F5 dependency graph.
 *
 * `computeDagreLayout` is a pure function: prerequisite -> mission edges,
 * `rankdir: LR`, fixed node sizes, and the Dagre centre coordinate converted to
 * the Vue Flow top-left origin (NEW_FUNCTION.md section 7).
 *
 * `useDagreLayout` wraps it with a structure signature so a pure status refresh
 * (new objects, same node ids and edges) keeps the existing coordinates and the
 * graph does not jump. Layout is applied synchronously from props, so a stale
 * filter response can never reach it: the view only hands over the latest
 * response (see WorkspaceView's request sequence). The generation counter is
 * kept for a future async measurement step.
 */
import dagre from '@dagrejs/dagre'
import { ref } from 'vue'
import type { XYPosition } from '@vue-flow/core'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import { NODE_HEIGHT, NODE_WIDTH } from '../workspace/dto'

export interface DagreLayoutOptions {
  rankdir?: 'LR' | 'TB'
  nodesep?: number
  ranksep?: number
}

export interface DagreLayoutResult {
  positions: Map<string, XYPosition>
  width: number
  height: number
}

/** Layout signature: only structure changes, never status or titles. */
export function graphStructureSignature(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
): string {
  const nodePart = [...nodes.map((node) => node.id)].sort().join(',')
  const edgePart = [...edges.map((edge) => `${edge.prerequisite_id}>${edge.mission_id}`)]
    .sort()
    .join(',')
  return `${nodePart}|${edgePart}`
}

export function computeDagreLayout(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
  options: DagreLayoutOptions = {},
): DagreLayoutResult {
  const graph = new dagre.graphlib.Graph()
  graph.setGraph({
    rankdir: options.rankdir ?? 'LR',
    nodesep: options.nodesep ?? 40,
    ranksep: options.ranksep ?? 88,
    marginx: 16,
    marginy: 16,
  })
  graph.setDefaultEdgeLabel(() => ({}))

  const ids = new Set(nodes.map((node) => node.id))
  for (const node of nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const edge of edges) {
    if (ids.has(edge.prerequisite_id) && ids.has(edge.mission_id)) {
      graph.setEdge(edge.prerequisite_id, edge.mission_id)
    }
  }

  dagre.layout(graph)

  const positions = new Map<string, XYPosition>()
  let width = 0
  let height = 0
  for (const node of nodes) {
    const point = graph.node(node.id) as { x: number; y: number } | undefined
    if (!point) continue
    // Dagre returns the centre; Vue Flow positions the top-left corner.
    const x = point.x - NODE_WIDTH / 2
    const y = point.y - NODE_HEIGHT / 2
    positions.set(node.id, { x, y })
    width = Math.max(width, x + NODE_WIDTH)
    height = Math.max(height, y + NODE_HEIGHT)
  }
  return { positions, width, height }
}

export function useDagreLayout() {
  let generation = 0
  const positions = ref<Map<string, XYPosition>>(new Map())
  const size = ref({ width: 0, height: 0 })
  const appliedSignature = ref('')

  /**
   * Recompute positions only when the structure changed (or `force` is set).
   * Returns true when new coordinates were applied.
   */
  function update(
    nodes: WorkspaceNode[],
    edges: WorkspaceEdge[],
    { force = false }: { force?: boolean } = {},
  ): boolean {
    const signature = graphStructureSignature(nodes, edges)
    if (!force && signature === appliedSignature.value) return false

    const token = ++generation
    const result = computeDagreLayout(nodes, edges)
    // Guard against an older layout overwriting a newer one.
    if (token !== generation) return false

    positions.value = result.positions
    size.value = { width: result.width, height: result.height }
    appliedSignature.value = signature
    return true
  }

  function reset() {
    generation += 1
    appliedSignature.value = ''
    positions.value = new Map()
    size.value = { width: 0, height: 0 }
  }

  return { positions, size, update, reset }
}
