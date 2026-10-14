/**
 * Parent/child grouping for the F5 dependency graph.
 *
 * The graph option "显示父子任务关系" mounts every child card directly under its
 * parent card (one vertical stack per family root) and lets a parent collapse
 * its subtree. Collapsing must not lose information: a hidden child's
 * dependencies are re-pointed to the collapsed ancestor, and edges that end up
 * inside the same collapsed subtree are dropped.
 *
 * Everything here is pure and derived from the read-only API payload
 * (`parent_edges` drives the structure). It never writes to the business API
 * and never invents relations the backend did not return.
 */
import type { WorkspaceEdge, WorkspaceNode, WorkspaceParentEdge } from '../api/types'
import type { LayoutGroup } from './dto'

export interface MissionForest {
  /** child id -> parent id, only when the parent is loaded. */
  parentOf: Map<string, string>
  /** parent id -> direct child ids in node order. */
  childrenOf: Map<string, string[]>
  /** Nodes without a loaded parent, in node order. */
  roots: string[]
  /** Nesting depth from the family root (0 for roots). */
  depth: Map<string, number>
  /** Descendant count (whole subtree, excluding the node itself). */
  descendantCount: Map<string, number>
}

export interface GroupedGraph {
  /** Visible nodes in forest pre-order (children directly after their parent). */
  nodes: WorkspaceNode[]
  /** Dependency edges after hidden children were merged onto their ancestor. */
  edges: WorkspaceEdge[]
  /** Dagre blocks: one per family root, members stacked vertically. */
  groups: LayoutGroup[]
  /** Visible child -> visible parent, for revealing a collapsed node. */
  parentOf: Map<string, string>
  /** Visible direct children per node. */
  childCount: Map<string, number>
  /** Total descendants (whole subtree, collapsed ones included) per node. */
  descendantCount: Map<string, number>
  /** Nesting depth per visible node (0 = family root). */
  depth: Map<string, number>
  /** Visible nodes whose subtree is collapsed. */
  collapsed: Set<string>
  /** Nodes hidden behind a collapsed ancestor. */
  hidden: Set<string>
}

/**
 * Build the parent/child forest from `parent_edges`. Self references, cycles and
 * parents outside the loaded node set are ignored, so a malformed payload can
 * never make the traversal loop.
 */
export function buildForest(
  nodes: WorkspaceNode[],
  parentEdges: WorkspaceParentEdge[],
): MissionForest {
  const order = new Map(nodes.map((node, index) => [node.id, index]))
  const present = new Set(nodes.map((node) => node.id))
  const parentOf = new Map<string, string>()

  for (const edge of parentEdges) {
    if (edge.parent_id === edge.child_id) continue
    if (!present.has(edge.parent_id) || !present.has(edge.child_id)) continue
    if (parentOf.has(edge.child_id)) continue

    // Walk up from the candidate parent: refuse an edge that would form a cycle.
    let cursor: string | undefined = edge.parent_id
    let cyclic = false
    const seen = new Set<string>()
    while (cursor) {
      if (cursor === edge.child_id || seen.has(cursor)) {
        cyclic = true
        break
      }
      seen.add(cursor)
      cursor = parentOf.get(cursor)
    }
    if (cyclic) continue

    parentOf.set(edge.child_id, edge.parent_id)
  }

  const childrenOf = new Map<string, string[]>()
  for (const [child, parent] of parentOf) {
    const list = childrenOf.get(parent) ?? []
    list.push(child)
    childrenOf.set(parent, list)
  }
  for (const list of childrenOf.values()) {
    list.sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0))
  }

  const roots = nodes.filter((node) => !parentOf.has(node.id)).map((node) => node.id)
  const depth = new Map<string, number>()
  const descendantCount = new Map<string, number>()
  const visited = new Set<string>()

  const measure = (id: string, level: number): number => {
    if (visited.has(id)) return 0
    visited.add(id)
    depth.set(id, level)
    let total = 0
    for (const child of childrenOf.get(id) ?? []) {
      total += 1 + measure(child, level + 1)
    }
    descendantCount.set(id, total)
    return total
  }
  for (const root of roots) measure(root, 0)

  return { parentOf, childrenOf, roots, depth, descendantCount }
}

/**
 * Apply the grouping option and the collapse set to the loaded graph.
 *
 * `collapsed` only takes effect for nodes that actually have children; unknown
 * or historical ids are ignored.
 */
export function groupByParent(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
  parentEdges: WorkspaceParentEdge[],
  collapsed: Set<string>,
): GroupedGraph {
  const forest = buildForest(nodes, parentEdges)
  const byId = new Map(nodes.map((node) => [node.id, node]))

  const visible: string[] = []
  const visibleSet = new Set<string>()
  const hidden = new Set<string>()
  const collapsedIds = new Set<string>()
  const representative = new Map<string, string>()
  const depth = new Map<string, number>()
  const membersOfRoot = new Map<string, string[]>()

  const markHidden = (id: string, root: string) => {
    for (const child of forest.childrenOf.get(id) ?? []) {
      if (hidden.has(child)) continue
      hidden.add(child)
      representative.set(child, root)
      markHidden(child, root)
    }
  }

  const visit = (id: string, level: number, root: string) => {
    if (visibleSet.has(id)) return
    visibleSet.add(id)
    visible.push(id)
    representative.set(id, id)
    depth.set(id, level)
    const members = membersOfRoot.get(root) ?? []
    members.push(id)
    membersOfRoot.set(root, members)

    const children = forest.childrenOf.get(id) ?? []
    if (children.length && collapsed.has(id)) {
      collapsedIds.add(id)
      markHidden(id, id)
      return
    }
    for (const child of children) visit(child, level + 1, root)
  }
  for (const root of forest.roots) visit(root, 0, root)

  // Edges: re-point hidden endpoints to the collapsed ancestor, drop internal
  // ones, and fold duplicates that now share the same visible pair.
  const merged: WorkspaceEdge[] = []
  const mergedIndex = new Map<string, number>()
  for (const edge of edges) {
    const source = representative.get(edge.prerequisite_id)
    const target = representative.get(edge.mission_id)
    if (!source || !target || source === target) continue
    const key = `${source}>${target}`
    const existing = mergedIndex.get(key)
    if (existing === undefined) {
      mergedIndex.set(key, merged.length)
      const from = byId.get(source)
      const to = byId.get(target)
      merged.push({
        id: edge.id,
        prerequisite_id: source,
        mission_id: target,
        is_satisfied: edge.is_satisfied,
        cross_milestone: !!from && !!to && from.milestone_id !== to.milestone_id,
      })
    } else {
      // Several hidden edges collapse into one: only ever "satisfied" when all
      // of them are, so a merge can never overstate readiness.
      merged[existing].is_satisfied = merged[existing].is_satisfied && edge.is_satisfied
    }
  }

  // Visible direct children, plus the subtree total (collapsed ones included so
  // a folded parent can still say how many subtasks it hides).
  const childCount = new Map<string, number>()
  const descendantCount = new Map<string, number>()
  for (const id of visible) {
    let count = 0
    for (const child of forest.childrenOf.get(id) ?? []) {
      if (!hidden.has(child)) count += 1
    }
    childCount.set(id, count)
    descendantCount.set(id, forest.descendantCount.get(id) ?? 0)
  }

  const groups: LayoutGroup[] = forest.roots
    .filter((root) => visibleSet.has(root))
    .map((root) => {
      const memberIds = (membersOfRoot.get(root) ?? [root]).filter((id) => visibleSet.has(id))
      return {
        id: root,
        memberIds,
        depths: memberIds.map((id) => depth.get(id) ?? 0),
      }
    })

  const parentOf = new Map<string, string>()
  for (const id of visible) {
    const parent = forest.parentOf.get(id)
    if (parent && visibleSet.has(parent)) parentOf.set(id, parent)
  }

  return {
    nodes: visible.map((id) => byId.get(id) as WorkspaceNode),
    edges: merged,
    groups,
    parentOf,
    childCount,
    descendantCount,
    depth,
    collapsed: collapsedIds,
    hidden,
  }
}

/** Expand every ancestor of `id` so a hidden target becomes visible again. */
export function revealPath(
  nodes: WorkspaceNode[],
  parentEdges: WorkspaceParentEdge[],
  collapsed: Set<string>,
  id: string,
): Set<string> {
  const forest = buildForest(nodes, parentEdges)
  const next = new Set(collapsed)
  let cursor = forest.parentOf.get(id)
  const seen = new Set<string>()
  while (cursor) {
    if (seen.has(cursor)) break
    seen.add(cursor)
    next.delete(cursor)
    cursor = forest.parentOf.get(cursor)
  }
  return next
}
