/** F5 read-only workspace aggregations: milestone board + dependency graph. */
import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type { WorkspaceGraph, WorkspaceOverview } from './types'

export const getWorkspaceOverview = (params: QueryParams = {}): Promise<WorkspaceOverview> =>
  request<WorkspaceOverview>('GET', `/api/workspace/overview/${buildQuery(params)}`)

export const getWorkspaceGraph = (params: QueryParams = {}): Promise<WorkspaceGraph> =>
  request<WorkspaceGraph>('GET', `/api/workspace/graph/${buildQuery(params)}`)
