/**
 * Dagre layout for the F5 dependency graph.
 *
 * `computeDagreLayout` is a pure function: prerequisite -> mission edges,
 * `rankdir: LR`, fixed node sizes, and the Dagre centre coordinate converted to
 * the Vue Flow top-left origin (NEW_FUNCTION.md section 7).
 *
 * With parent/child grouping enabled, a family (root + visible descendants) is
 * handed to Dagre as a single block sized to hold the whole vertical stack, so
 * children are mounted directly under their parent while the dependency ranks
 * still decide the column. Dependency edges are remapped onto the family roots
 * by the caller, so collapsing a subtree never changes the columns.
 *
 * `useDagreLayout` wraps it with a structure signature so a pure status refresh
 * (new objects, same node ids/edges/groups) keeps the existing coordinates and
 * the graph does not jump. Layout is applied synchronously from props, so a
 * stale filter response can never reach it.
 */
import dagre from '@dagrejs/dagre'
import { ref } from 'vue'
import type { XYPosition } from '@vue-flow/core'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import { GROUP_GAP, GROUP_INDENT, NODE_HEIGHT, NODE_WIDTH } from '../workspace/dto'
import type { LayoutGroup } from '../workspace/dto'

export interface DagreLayoutOptions {
  rankdir?: 'LR' | 'TB'
  nodesep?: number
  ranksep?: number
  /** Parent/child stacks; omit to lay out every node independently. */
  groups?: LayoutGroup[] | null
}

export interface DagreLayoutResult {
  positions: Map<string, XYPosition>
  width: number
  height: number
}

function blockSize(group: LayoutGroup): { width: number; height: number } {
  const levels = group.depths.length ? Math.max(...group.depths) : 0
  return {
    width: NODE_WIDTH + levels * GROUP_INDENT,
    height: group.memberIds.length * (NODE_HEIGHT + GROUP_GAP) - GROUP_GAP,
  }
}

/** One Dagre block per node when no grouping is supplied. */
function toGroups(nodes: WorkspaceNode[], groups?: LayoutGroup[] | null): LayoutGroup[] {
  if (groups && groups.length) return groups
  return nodes.map((node) => ({ id: node.id, memberIds: [node.id], depths: [0] }))
}

/** Layout signature: only structure changes, never status or titles. */
export function graphStructureSignature(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
  groups?: LayoutGroup[] | null,
): string {
  const blocks = toGroups(nodes, groups)
    .map((group) => `${group.id}[${group.memberIds.join('>')}]`)
    .sort()
    .join(',')
  const edgePart = [...edges.map((edge) => `${edge.prerequisite_id}>${edge.mission_id}`)]
    .sort()
    .join(',')
  return `${blocks}|${edgePart}`
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

  const blocks = toGroups(nodes, options.groups)
  const ids = new Set(blocks.map((block) => block.id))
  const sizes = new Map<string, { width: number; height: number }>()
  for (const block of blocks) {
    const size = blockSize(block)
    sizes.set(block.id, size)
    graph.setNode(block.id, size)
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
  for (const block of blocks) {
    const point = graph.node(block.id) as { x: number; y: number } | undefined
    const size = sizes.get(block.id)
    if (!point || !size) continue
    // Dagre returns the block centre; Vue Flow positions the top-left corner.
    const left = point.x - size.width / 2
    const top = point.y - size.height / 2
    block.memberIds.forEach((memberId, index) => {
      positions.set(memberId, {
        x: left + (block.depths[index] ?? 0) * GROUP_INDENT,
        y: top + index * (NODE_HEIGHT + GROUP_GAP),
      })
    })
    width = Math.max(width, left + size.width)
    height = Math.max(height, top + size.height)
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
    { force = false, groups }: { force?: boolean; groups?: LayoutGroup[] | null } = {},
  ): boolean {
    const signature = graphStructureSignature(nodes, edges, groups)
    if (!force && signature === appliedSignature.value) return false

    const token = ++generation
    const result = computeDagreLayout(nodes, edges, { groups })
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
