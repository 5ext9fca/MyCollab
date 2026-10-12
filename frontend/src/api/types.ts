export interface User {
  id: number
  username: string
  display_name: string
}

/** Current session user; adds the staff flag the SPA uses for route guards. */
export interface CurrentUser extends User {
  is_staff: boolean
}

export interface Member extends User {
  email: string
  is_active: boolean
  is_staff: boolean
  date_joined: string
}

export type RegistrationStatus = 'Pending' | 'Approved' | 'Rejected'

export interface RegistrationRequest {
  id: string
  username: string
  email: string
  display_name: string
  message: string
  status: RegistrationStatus
  review_note: string
  reviewed_by: User | null
  reviewed_at: string | null
  created_at: string
}

export interface Tag {
  id: string
  name: string
}

export type MissionStatus = 'Open' | 'InProgress' | 'Submitted' | 'Done' | 'Cancelled'

export interface Mission {
  id: string
  title: string
  status: MissionStatus
  creator: User
  assignee: User | null
  parent: string | null
  tags: Tag[]
  version: number
  created_at: string
  updated_at: string
  allowed_actions: string[]
  content?: string
  acceptance_criteria?: string
  result?: string
  children?: Mission[]
}

export interface MissionEvent {
  id: number
  actor: User
  action: string
  payload: Record<string, unknown>
  created_at: string
}

export interface Comment {
  id: string
  mission: string
  author: User
  content: string
  created_at: string
  updated_at: string
  can_edit: boolean
}

export interface LibraryFile {
  id: string
  original_name: string
  content_type: string
  size: number
  /** Authorized download URL; the value Markdown should reference. */
  url: string
  created_at: string
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface MissionWritePayload {
  title: string
  content?: string
  acceptance_criteria?: string
  tags?: string[]
  parent?: string | null
}
