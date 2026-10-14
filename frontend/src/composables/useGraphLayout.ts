/**
 * Top-down layered layout for the F5 dependency graph (NEW_FUNCTION.md).
 *
 * The canvas reads top to bottom: every card sits strictly below all of its
 * visible prerequisites. When "显示父子任务关系" is on, a parent also sits left of
 * its children, which expand to the right. The previous "one Dagre block per
 * family" approach cannot express this because it hid each child's own
 * dependency level, so the layering is computed here explicitly:
 *
 * 1. `dependencyLevels` layers the visible dependency DAG (the row). A node
 *    without a visible prerequisite is level 0; every other node is
 *    `1 + max(level of its visible prerequisites)`. Edges that would close a
 *    cycle are not used as a layering constraint; the anomaly is reported so the
 *    page can warn instead of drawing a graph that violates the edge direction.
 * 2. Each family (root + visible descendants) gets local columns: the root is
 *    column 0 and a child is placed at least one column right of its parent,
 *    never sharing a (column, row) cell with another family member. Depth grows
 *    to the right while the row still comes from the dependency level.
 * 3. Families are packed left to right. Families whose row ranges overlap get
 *    disjoint column bands, so a parent's reserved region can never be intruded
 *    on by another task or family and cards never overlap.
 *
 * Everything here is a pure function of the visible nodes, the visible edges and
 * the visible parent/child structure, so identical structure and sizes always
 * produce identical coordinates. `graphStructureSignature` lets a status-only
 * refresh keep the existing coordinates instead of moving the canvas.
 */
import { ref } from 'vue'
import type { XYPosition } from '@vue-flow/core'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import { NODE_HEIGHT, NODE_WIDTH } from '../workspace/dto'

/** Horizontal space between two card columns. */
export const GRAPH_H_GAP = 36
/** Vertical space between two dependency levels. */
export const GRAPH_V_GAP = 56

export interface DependencyLayerResult {
  /** Node id -> dependency level (row), top to bottom. */
  levels: Map<string, number>
  /** True when a dependency cycle had to be broken to keep the graph drawable. */
  hasCycle: boolean
}

/**
 * Layered levels for the visible dependency graph.
 *
 * Only visible edges count: an edge whose endpoints are not both loaded is not a
 * layering constraint (the backend already flags the incomplete relation), and
 * an unloaded prerequisite must never be read as "no prerequisite".
 */
export function dependencyLevels(
  nodeIds: string[],
  edges: Array<Pick<WorkspaceEdge, 'prerequisite_id' | 'mission_id'>>,
): DependencyLayerResult {
  const present = new Set(nodeIds)
  const prerequisites = new Map<string, string[]>()
  for (const edge of edges) {
    const { prerequisite_id, mission_id } = edge
    if (prerequisite_id === mission_id) continue
    if (!present.has(prerequisite_id) || !present.has(mission_id)) continue
    const list = prerequisites.get(mission_id)
    if (!list) prerequisites.set(mission_id, [prerequisite_id])
    else if (!list.includes(prerequisite_id)) list.push(prerequisite_id)
  }

  const levels = new Map<string, number>()
  // `1 + max(level of every visible prerequisite)`, resolving without a queue so
  // the result only depends on the node set, never on the input array order.
  let changed = true
  while (changed) {
    changed = false
    for (const id of nodeIds) {
      if (levels.has(id)) continue
      const predecessors = prerequisites.get(id) ?? []
      if (!predecessors.every((item) => levels.has(item))) continue
      let level = 0
      for (const item of predecessors) level = Math.max(level, (levels.get(item) ?? 0) + 1)
      levels.set(id, level)
      changed = true
    }
  }

  // Anything left sits on a cycle: keep it drawable using the already layered
  // prerequisites and report the anomaly.
  const unresolved = nodeIds.filter((id) => !levels.has(id))
  for (const id of unresolved) {
    let level = 0
    for (const item of prerequisites.get(id) ?? []) {
      if (!levels.has(item)) continue
      level = Math.max(level, (levels.get(item) ?? 0) + 1)
    }
    levels.set(id, level)
  }

  return { levels, hasCycle: unresolved.length > 0 }
}

/** One family (root + visible descendants) before it is packed horizontally. */
interface FamilyLayout {
  root: string
  /** Node id -> local column (0 = the family root). */
  columns: Map<string, number>
  /** Number of columns the family occupies. */
  width: number
  /** Lowest / highest dependency level used by the family. */
  rowStart: number
  rowEnd: number
}

/**
 * Local columns for one family: depth-first, so a parent is always placed before
 * its children, and a child always at least one column right of its parent. A
 * (column, row) cell already taken by a family member pushes the child further
 * right, which keeps sibling subtasks from overlapping their uncles.
 */
function layoutFamily(
  root: string,
  childrenOf: Map<string, string[]>,
  levels: Map<string, number>,
): FamilyLayout {
  const columns = new Map<string, number>()
  const used = new Set<string>()

  const place = (id: string, parentColumn: number | null) => {
    if (columns.has(id)) return
    const row = levels.get(id) ?? 0
    let column = parentColumn === null ? 0 : parentColumn + 1
    while (used.has(`${column}:${row}`)) column += 1
    columns.set(id, column)
    used.add(`${column}:${row}`)
    for (const child of childrenOf.get(id) ?? []) {
      if (!levels.has(child)) continue
      place(child, column)
    }
  }
  place(root, null)

  let width = 0
  let rowStart = Number.POSITIVE_INFINITY
  let rowEnd = Number.NEGATIVE_INFINITY
  for (const [id, column] of columns) {
    width = Math.max(width, column + 1)
    const row = levels.get(id) ?? 0
    rowStart = Math.min(rowStart, row)
    rowEnd = Math.max(rowEnd, row)
  }
  return { root, columns, width, rowStart, rowEnd }
}

export interface GraphLayoutOptions {
  /** Visible parent -> visible children; null treats every node as its own family. */
  childrenOf?: Map<string, string[]> | null
}

export interface GraphLayoutResult {
  positions: Map<string, XYPosition>
  levels: Map<string, number>
  width: number
  height: number
  hasCycle: boolean
}

export function computeGraphLayout(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
  options: GraphLayoutOptions = {},
): GraphLayoutResult {
  const nodeIds = nodes.map((node) => node.id)
  const { levels, hasCycle } = dependencyLevels(nodeIds, edges)
  const childrenOf = options.childrenOf ?? null

  const families: FamilyLayout[] = []
  if (childrenOf) {
    const hasParent = new Set<string>()
    for (const children of childrenOf.values()) {
      for (const child of children) hasParent.add(child)
    }
    for (const id of nodeIds) {
      if (hasParent.has(id)) continue
      families.push(layoutFamily(id, childrenOf, levels))
    }
    // Defensive: a node the structure did not reach is laid out on its own.
    const covered = new Set<string>()
    for (const family of families) for (const id of family.columns.keys()) covered.add(id)
    for (const id of nodeIds) {
      if (!covered.has(id)) families.push(layoutFamily(id, new Map(), levels))
    }
  } else {
    for (const id of nodeIds) {
      const row = levels.get(id) ?? 0
      families.push({
        root: id,
        columns: new Map([[id, 0]]),
        width: 1,
        rowStart: row,
        rowEnd: row,
      })
    }
  }

  // Pack families left to right: two families whose row ranges overlap must not
  // share columns, so their reserved regions stay disjoint.
  const orderIndex = new Map(nodeIds.map((id, index) => [id, index]))
  const ordered = [...families].sort(
    (a, b) =>
      a.rowStart - b.rowStart || (orderIndex.get(a.root) ?? 0) - (orderIndex.get(b.root) ?? 0),
  )
  const offsets = new Map<string, number>()
  const placed: FamilyLayout[] = []
  for (const family of ordered) {
    let offset = 0
    for (const other of placed) {
      if (other.rowEnd < family.rowStart) continue
      offset = Math.max(offset, (offsets.get(other.root) ?? 0) + other.width)
    }
    offsets.set(family.root, offset)
    placed.push(family)
  }

  const positions = new Map<string, XYPosition>()
  let width = 0
  let height = 0
  for (const family of ordered) {
    const offset = offsets.get(family.root) ?? 0
    for (const [id, column] of family.columns) {
      const x = (offset + column) * (NODE_WIDTH + GRAPH_H_GAP)
      const y = (levels.get(id) ?? 0) * (NODE_HEIGHT + GRAPH_V_GAP)
      positions.set(id, { x, y })
      width = Math.max(width, x + NODE_WIDTH)
      height = Math.max(height, y + NODE_HEIGHT)
    }
  }

  return { positions, levels, width, height, hasCycle }
}

/** Layout signature: only structure and card size, never status, titles or dates. */
export function graphStructureSignature(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
  childrenOf?: Map<string, string[]> | null,
): string {
  const nodePart = nodes.map((node) => node.id).join(',')
  const edgePart = edges
    .map((edge) => `${edge.prerequisite_id}>${edge.mission_id}`)
    .sort()
    .join(',')
  const familyPart = childrenOf
    ? [...childrenOf.entries()]
        .map(([parent, children]) => `${parent}[${[...children].sort().join('>')}]`)
        .sort()
        .join(',')
    : ''
  return `${NODE_WIDTH}x${NODE_HEIGHT}|${nodePart}|${edgePart}|${familyPart}`
}

export function useGraphLayout() {
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
    {
      force = false,
      childrenOf = null,
    }: { force?: boolean; childrenOf?: Map<string, string[]> | null } = {},
  ): boolean {
    const signature = graphStructureSignature(nodes, edges, childrenOf)
    if (!force && signature === appliedSignature.value) return false

    const token = ++generation
    const result = computeGraphLayout(nodes, edges, { childrenOf })
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
