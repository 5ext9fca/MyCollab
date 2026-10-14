/**
 * Display-only graph traversal over the *already loaded* edges (F5).
 *
 * These helpers decide which nodes to highlight or dim; they never infer a
 * business conclusion. `is_blocked`, edge satisfaction and allowed actions all
 * come from the backend. A graph truncated by the server cannot be walked "to
 * the end", so callers combine the result with `meta.relationships_complete`
 * before claiming a node has no further relations.
 */
import type { WorkspaceEdge } from '../api/types'

export type TraversalDirection = 'upstream' | 'downstream' | 'both'

export interface DirectRelations {
  prerequisites: Set<string>
  dependents: Set<string>
}

/** Direct prerequisites and dependents of a node, from the visible edges. */
export function directRelations(id: string, edges: WorkspaceEdge[]): DirectRelations {
  const prerequisites = new Set<string>()
  const dependents = new Set<string>()
  for (const edge of edges) {
    if (edge.mission_id === id) prerequisites.add(edge.prerequisite_id)
    if (edge.prerequisite_id === id) dependents.add(edge.mission_id)
  }
  return { prerequisites, dependents }
}

/**
 * Walk the loaded graph from `startId` in one direction.
 *
 * Returns every reachable id (excluding the start). Cycles are handled with a
 * visited set; `limit` stops a runaway walk on a very large graph.
 */
export function collectRelated(
  startId: string,
  edges: WorkspaceEdge[],
  direction: TraversalDirection,
  limit = Number.POSITIVE_INFINITY,
): string[] {
  const prerequisites = new Map<string, string[]>()
  const dependents = new Map<string, string[]>()
  for (const edge of edges) {
    if (direction !== 'downstream') {
      const list = prerequisites.get(edge.mission_id) ?? []
      list.push(edge.prerequisite_id)
      prerequisites.set(edge.mission_id, list)
    }
    if (direction !== 'upstream') {
      const list = dependents.get(edge.prerequisite_id) ?? []
      list.push(edge.mission_id)
      dependents.set(edge.prerequisite_id, list)
    }
  }

  const visited = new Set<string>([startId])
  const ids: string[] = []
  const queue: string[] = [startId]
  while (queue.length) {
    const current = queue.shift()!
    const next = [
      ...(direction !== 'downstream' ? (prerequisites.get(current) ?? []) : []),
      ...(direction !== 'upstream' ? (dependents.get(current) ?? []) : []),
    ]
    for (const neighbor of next) {
      if (visited.has(neighbor)) continue
      visited.add(neighbor)
      ids.push(neighbor)
      if (ids.length >= limit) return ids
      queue.push(neighbor)
    }
  }
  return ids
}

/** Highlight set for "only what is related": the start plus every reachable id. */
export function relatedHighlight(
  startId: string,
  edges: WorkspaceEdge[],
  direction: TraversalDirection,
): Set<string> {
  return new Set<string>([startId, ...collectRelated(startId, edges, direction)])
}
