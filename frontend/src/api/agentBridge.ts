import { request } from './client'
import type { Paginated } from './types'

export type AssistanceKind = 'design_polish' | 'template_generate' | 'mission_write' | 'review_assist'
export type ImageKind = 'image_generate' | 'image_edit'
export type AgentCapability = AssistanceKind | ImageKind
export interface AgentDevice {
  id: string; name: string; capabilities: AgentCapability[]; expires_at: string
  revoked_at: string | null; last_seen_at: string | null
}
export interface AssistanceRequest {
  id: string; kind: AssistanceKind; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'expired'
  input: Record<string, unknown>; result: Record<string, unknown> | null; error: string
  stale_reason: string; stopped_at: string | null; created_at: string
}
export interface AssistanceInput {
  device_id: string; kind: AssistanceKind; idempotency_key: string; draft: Record<string, unknown>
  instructions: string; context_ids: string[]; object_id?: string | null; base_version?: number | null
  submission_id?: string | null; parent_id?: string | null; retry_of?: string | null
  comment_ids?: string[]
}
export type AssistanceSummary = Pick<AssistanceRequest, 'id' | 'error' | 'stopped_at' | 'created_at'> & { kind: AgentCapability; status: AssistanceRequest['status'] | 'awaiting_selection' }
export const listAgentDevices = () => request<Paginated<AgentDevice>>('GET', '/api/agent-devices/?page_size=100')
export const createAgentDevice = (name: string, capabilities: AgentCapability[], expires_days: number) =>
  request<AgentDevice & { token: string }>('POST', '/api/agent-devices/', { name, capabilities, expires_days })
export const revokeAgentDevice = (id: string) => request<AgentDevice>('POST', `/api/agent-devices/${id}/revoke/`, {})
export const createAssistance = (input: AssistanceInput) => request<AssistanceRequest>('POST', '/api/assistance-requests/', input)
export const getAssistance = (id: string) => request<AssistanceRequest>('GET', `/api/assistance-requests/${id}/`)
export const cancelAssistance = (id: string) => request<AssistanceRequest>('POST', `/api/assistance-requests/${id}/cancel/`, {})
export const listAssistance = (page = 1) => request<Paginated<AssistanceSummary>>('GET', `/api/assistance-requests/?page=${page}`)
