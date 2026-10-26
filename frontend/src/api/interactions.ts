import { request } from './client'
export interface InteractionEvent {
  seq: number; kind: 'assistant_message' | 'permission_requested' | 'permission_closed'
  payload: { text?: string }; created_at: string
}
export interface InteractionPermission {
  permission_id: string; operation: { action: 'edit'; paths: string[] }; operation_digest: string
  status: string; decision: string; expires_at: string
}
export interface InteractionCommand {
  command_id: string; kind: 'followup' | 'permission_reply'; payload: { text?: string; decision?: string }
  status: string; created_at: string
}
export interface InteractionState {
  available: boolean; active: boolean; attempt_id?: string; session_nonce?: string
  supports_followup?: boolean; supports_permissions?: boolean
  events: InteractionEvent[]; permissions: InteractionPermission[]; commands: InteractionCommand[]
  next_cursor?: number; has_more?: boolean
}
export interface InteractionInput {
  attempt_id: string; session_nonce: string; command_id: string
  kind: 'followup' | 'permission_reply'
  payload: { text: string } | { permission_id: string; operation_digest: string; decision: 'approve' | 'deny' }
}
export const getInteraction = (id: string, after = 0) => request<InteractionState>('GET', `/api/assistance-requests/${id}/interaction/?after=${after}`)
export const sendInteraction = (id: string, input: InteractionInput) => request<{command_id: string; status: string}>('POST', `/api/assistance-requests/${id}/interaction/`, input)
