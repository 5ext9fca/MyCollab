import { request } from './client'
import type { Paginated } from './types'

export interface CodeReport {
  schema_version: 1; source: 'local_runner'; base_commit: string; summary: string
  changed_files: { path: string; change: 'added' | 'modified' | 'deleted' }[]
  verification: { id: string; label: string; status: 'passed' | 'failed' | 'timeout' | 'not_run'; exit_code: number | null; duration_ms: number }[]
}
export interface CodeExecution {
  id: string; request_id: string; mission_id: string; actor_id: number; mission_version: number
  repository_key: string; version: number; previous_id: string | null
  status: 'queued' | 'running' | 'awaiting_selection' | 'succeeded' | 'failed' | 'cancelled' | 'expired'
  manifest: { base_commit?: string; patch_sha256?: string; patch_size?: number; report_sha256?: string; report_size?: number }
  report: CodeReport | null; patch_url: string | null; stale_reason: string; error: string
  expires_at: string; stopped_at: string | null; created_at: string; published_at: string | null
}
export interface CodeInput {
  mission_id: string; device_id: string; repository_key: string; expected_version: number
  instructions: string; idempotency_key: string; previous_id?: string | null
}
export const listCodeExecutions = (mission: string, page = 1) => request<Paginated<CodeExecution>>('GET', `/api/code-executions/?mission=${mission}&page=${page}`)
export const createCodeExecution = (input: CodeInput) => request<CodeExecution>('POST', '/api/code-executions/', input)
export const getCodeExecution = (id: string) => request<CodeExecution>('GET', `/api/code-executions/${id}/`)
export const cancelCodeExecution = (id: string) => request<CodeExecution>('POST', `/api/code-executions/${id}/cancel/`, {})
