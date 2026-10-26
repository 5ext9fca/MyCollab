import { request } from './client'
import type { ImageKind } from './agentBridge'
import type { Paginated } from './types'

export interface ExecutionCandidate {
  id: string; key: string; name: string; sha256: string; size: number; width: number; height: number
  file_id: string | null; url: string | null; uploaded_at: string | null
}
export interface MissionExecution {
  id: string; request_id: string; mission_id: string; asset_id: string; actor_id: number
  mission_version: number; asset_version: number; version: number; previous_id: string | null
  kind: ImageKind; status: 'queued' | 'running' | 'awaiting_selection' | 'succeeded' | 'failed' | 'cancelled' | 'expired'
  selected_ids: string[]; candidates: ExecutionCandidate[]; stale_reason: string; expires_at: string
  error: string; stopped_at: string | null; created_at: string
}
export interface ExecutionInput {
  mission_id: string; asset_id: string; device_id: string; kind: ImageKind; expected_version: number
  asset_version: number; instructions: string; reference_ids: string[]; idempotency_key: string
  previous_id?: string | null
}
export const listExecutions = (mission: string, page = 1) => request<Paginated<MissionExecution>>('GET', `/api/mission-executions/?mission=${mission}&page=${page}`)
export const createExecution = (input: ExecutionInput) => request<MissionExecution>('POST', '/api/mission-executions/', input)
export const getExecution = (id: string) => request<MissionExecution>('GET', `/api/mission-executions/${id}/`)
export const cancelExecution = (id: string) => request<MissionExecution>('POST', `/api/mission-executions/${id}/cancel/`, {})
