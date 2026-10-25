import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type {
  Mission,
  MissionCreatePayload,
  MissionDependencyResponse,
  MissionEvent,
  MissionSubmission,
  MissionUpdatePayload,
  Paginated,
  ReviewPayload,
  SubmitPayload,
  Tag,
} from './types'

export type MissionQuery = QueryParams

export const listMissions = (params: MissionQuery = {}): Promise<Paginated<Mission>> =>
  request<Paginated<Mission>>('GET', `/api/missions/${buildQuery(params)}`)

export const getMission = (id: string): Promise<Mission> =>
  request<Mission>('GET', `/api/missions/${id}/`)

export const createMission = (payload: MissionCreatePayload): Promise<Mission> =>
  request<Mission>('POST', '/api/missions/', payload)

/** Every write to an existing mission must carry the current `expected_version`. */
export const updateMission = (id: string, payload: MissionUpdatePayload): Promise<Mission> =>
  request<Mission>('PATCH', `/api/missions/${id}/`, payload)

export const claimMission = (id: string, expectedVersion: number): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/claim/`, { expected_version: expectedVersion })

export const releaseMission = (id: string, expectedVersion: number): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/release/`, { expected_version: expectedVersion })

export const submitMission = (
  id: string,
  payload: SubmitPayload,
  expectedVersion: number,
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/submit/`, {
    ...payload,
    expected_version: expectedVersion,
  })

export const reviewMission = (
  id: string,
  payload: ReviewPayload,
  expectedVersion: number,
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/review/`, {
    ...payload,
    expected_version: expectedVersion,
  })

export const transferReview = (
  id: string,
  newReviewerId: number,
  reason: string,
  expectedVersion: number,
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/transfer-review/`, {
    new_reviewer_id: newReviewerId,
    reason,
    expected_version: expectedVersion,
  })

export const reopenMission = (
  id: string,
  reason: string,
  expectedVersion: number,
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/reopen/`, {
    reason,
    expected_version: expectedVersion,
  })

export const cancelMission = (
  id: string,
  reason: string,
  expectedVersion: number,
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/cancel/`, {
    reason,
    expected_version: expectedVersion,
  })

export const listDependencies = (id: string): Promise<MissionDependencyResponse> =>
  request<MissionDependencyResponse>('GET', `/api/missions/${id}/dependencies/`)

export const addDependency = (
  id: string,
  prerequisiteId: string,
  expectedVersion: number,
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/dependencies/`, {
    prerequisite_id: prerequisiteId,
    expected_version: expectedVersion,
  })

export const removeDependency = (
  id: string,
  dependencyId: string,
  expectedVersion: number,
): Promise<void> =>
  request<void>(
    'DELETE',
    `/api/missions/${id}/dependencies/${dependencyId}/${buildQuery({ expected_version: expectedVersion })}`,
  )

export const listSubmissions = (
  id: string,
  params: QueryParams = {},
): Promise<Paginated<MissionSubmission>> =>
  request<Paginated<MissionSubmission>>('GET', `/api/missions/${id}/submissions/${buildQuery(params)}`)

export const listEvents = (id: string): Promise<Paginated<MissionEvent>> =>
  request<Paginated<MissionEvent>>('GET', `/api/missions/${id}/events/`)

export const listTags = (): Promise<Tag[]> => request<Tag[]>('GET', '/api/tags/')

export { buildQuery }

export interface BulkChanges { priority?: string; milestone?: string | null; planned_start_date?: string | null; planned_end_date?: string | null }
export interface BulkResult { id: string; success: boolean; status: number; mission?: Mission; error?: { code: string; message: string; field_errors: Record<string, string[]> } }
export const bulkUpdateMissions = (items: { id: string; expected_version: number }[], changes: BulkChanges) => request<{ results: BulkResult[]; succeeded_count: number; failed_count: number }>('POST', '/api/missions/bulk-update/', { items, changes })
