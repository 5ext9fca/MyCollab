import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type {
  Mission,
  MissionEvent,
  MissionWritePayload,
  Paginated,
  Tag,
} from './types'

export type MissionQuery = QueryParams

export const listMissions = (params: MissionQuery = {}): Promise<Paginated<Mission>> =>
  request<Paginated<Mission>>('GET', `/api/missions/${buildQuery(params)}`)

export const getMission = (id: string): Promise<Mission> =>
  request<Mission>('GET', `/api/missions/${id}/`)

export const createMission = (payload: MissionWritePayload): Promise<Mission> =>
  request<Mission>('POST', '/api/missions/', payload)

export const updateMission = (
  id: string,
  payload: Partial<MissionWritePayload> & { version: number },
): Promise<Mission> => request<Mission>('PATCH', `/api/missions/${id}/`, payload)

export const claimMission = (id: string): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/claim/`, {})

export const releaseMission = (id: string): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/release/`, {})

export const submitMission = (id: string, result: string): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/submit/`, { result })

export const reviewMission = (
  id: string,
  approve: boolean,
  comment = '',
): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/review/`, { approve, comment })

export const cancelMission = (id: string, reason = ''): Promise<Mission> =>
  request<Mission>('POST', `/api/missions/${id}/cancel/`, { reason })

export const listEvents = (id: string): Promise<Paginated<MissionEvent>> =>
  request<Paginated<MissionEvent>>('GET', `/api/missions/${id}/events/`)

export const listTags = (): Promise<Tag[]> => request<Tag[]>('GET', '/api/tags/')

export { buildQuery }
