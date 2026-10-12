import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type {
  Milestone,
  MilestoneCreatePayload,
  MilestoneStatus,
  MilestoneUpdatePayload,
  Paginated,
} from './types'

export const listMilestones = (params: QueryParams = {}): Promise<Paginated<Milestone>> =>
  request<Paginated<Milestone>>('GET', `/api/milestones/${buildQuery(params)}`)

export const getMilestone = (id: string): Promise<Milestone> =>
  request<Milestone>('GET', `/api/milestones/${id}/`)

export const createMilestone = (payload: MilestoneCreatePayload): Promise<Milestone> =>
  request<Milestone>('POST', '/api/milestones/', payload)

export const updateMilestone = (
  id: string,
  payload: MilestoneUpdatePayload,
): Promise<Milestone> => request<Milestone>('PATCH', `/api/milestones/${id}/`, payload)

/** Controlled status transition; restoring a closed milestone needs a reason. */
export const transitionMilestone = (
  id: string,
  status: MilestoneStatus,
  expectedVersion: number,
  reason = '',
): Promise<Milestone> =>
  request<Milestone>('POST', `/api/milestones/${id}/transition/`, {
    status,
    reason,
    expected_version: expectedVersion,
  })
