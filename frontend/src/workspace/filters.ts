/** Shared workspace filter shape (F5). Kept in a plain module so the filter
 * bar, the URL sync and the request builder all agree on one contract. */
import type { MissionPriority, MissionStatus, MissionType } from '../api/types'

export interface WorkspaceFilters {
  design_element?: string
  q: string
  milestone: string
  status: MissionStatus | ''
  type: MissionType | ''
  priority: MissionPriority | ''
  assignee: string
  reviewer: string
  blocked: '' | 'true' | 'false'
  revalidation: '' | 'true'
}

export type QuickKey = 'mine' | 'blocked' | 'review' | 'revalidation'

export function emptyFilters(): WorkspaceFilters {
  return {
    design_element: '',
    q: '',
    milestone: '',
    status: '',
    type: '',
    priority: '',
    assignee: '',
    reviewer: '',
    blocked: '',
    revalidation: '',
  }
}

/** Read a scalar query param, tolerating repeated params from the URL. */
export function readParam(value: unknown): string {
  if (Array.isArray(value)) return value.length ? String(value[0]) : ''
  return value == null ? '' : String(value)
}
