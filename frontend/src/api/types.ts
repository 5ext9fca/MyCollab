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

/** F1: a mission's kind; reuses the same state machine as `Task`. */
export type MissionType = 'Feature' | 'Task' | 'Bug'

/** F2: fixed priority enum; `P0` is the most urgent. */
export type MissionPriority = 'P0' | 'P1' | 'P2' | 'P3'

export type MilestoneStatus = 'Planned' | 'Active' | 'Completed' | 'Cancelled'

/** F4: build result, not the QA/review result. */
export type BuildStatus = 'Unknown' | 'Pending' | 'Succeeded' | 'Failed'

export type SubmissionOutcome = 'Pending' | 'Accepted' | 'Rejected'

export type SubmissionProvider = 'Git' | 'Perforce' | 'UVCS' | 'Other'

export interface MilestoneBrief {
  id: string
  name: string
  status: MilestoneStatus
  due_date: string | null
}

export interface MilestoneCounts {
  total: number
  effective_total: number
  done: number
  /** `null` when the milestone has no effective tasks (not 100%). */
  progress: number | null
}

export interface Milestone {
  id: string
  name: string
  description: string
  due_date: string | null
  status: MilestoneStatus
  version: number
  created_by: User
  created_at: string
  updated_at: string
  progress: number | null
  overdue: boolean
  mission_counts: MilestoneCounts
}

/** Lightweight mission reference returned by dependency lists. */
export interface MissionRef {
  id: string
  title: string
  status: MissionStatus
  type: MissionType
  priority: MissionPriority
}

/** A direct prerequisite plus the `MissionDependency` id used to remove it. */
export interface MissionPrerequisiteRef extends MissionRef {
  dependency_id: string
}

export interface Mission {
  id: string
  title: string
  status: MissionStatus
  type: MissionType
  priority: MissionPriority
  creator: User
  assignee: User | null
  /** F3: the user who accepts the work; `null` when it must be re-assigned. */
  reviewer: User | null
  parent: string | null
  milestone: MilestoneBrief | null
  tags: Tag[]
  version: number
  created_at: string
  updated_at: string
  allowed_actions: string[]
  // F1/F3 derived flags (never stored).
  has_unresolved_prerequisites: boolean
  is_blocked: boolean
  blocking_mission_ids: string[]
  unfinished_child_ids: string[]
  needs_dependency_review: boolean
  reviewer_missing: boolean
  milestone_closed: boolean
  content?: string
  acceptance_criteria?: string
  children?: Mission[]
  prerequisites?: MissionPrerequisiteRef[]
  dependents?: MissionRef[]
  current_submission?: string | null
}

export interface MissionDependencyResponse {
  prerequisites: MissionPrerequisiteRef[]
  dependents: MissionRef[]
  has_unresolved_prerequisites: boolean
}

export interface SubmissionSourceReference {
  id: string
  provider: SubmissionProvider
  repository: string
  revision: string
  browse_url: string
}

export interface SubmissionBuildReference {
  id: string
  provider: string
  build_id: string
  platform: string
  source_revision: string
  artifact_url: string
  status: BuildStatus
  verification_note: string
}

/** F3/F4: one immutable round of deliverables. */
export interface MissionSubmission {
  id: string
  mission: string
  submitted_by: User
  submitted_at: string
  description: string
  verification_description: string
  reviewer_snapshot: User | null
  outcome: SubmissionOutcome
  reviewed_by: User | null
  reviewed_at: string | null
  review_comment: string
  verified_build_reference: string | null
  source_references: SubmissionSourceReference[]
  build_references: SubmissionBuildReference[]
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

/**
 * Values emitted by `MissionForm`; the views map `reviewer_id` / `milestone_id`
 * onto the create (`reviewer_id`) or update (`reviewer`) API field names.
 */
export interface MissionFormValues {
  title: string
  content: string
  acceptance_criteria: string
  tags: string[]
  type: MissionType
  priority: MissionPriority
  reviewer_id: number | null
  milestone_id: string | null
}

/** Payload for `POST /api/missions/`; the server initialises `version`. */
export interface MissionCreatePayload {
  title: string
  content?: string
  acceptance_criteria?: string
  tags?: string[]
  parent?: string | null
  type?: MissionType
  priority?: MissionPriority
  reviewer_id?: number | null
  milestone_id?: string | null
}

/** Payload for `PATCH /api/missions/{id}/`; always carries `expected_version`. */
export interface MissionUpdatePayload {
  expected_version: number
  title?: string
  content?: string
  acceptance_criteria?: string
  tags?: string[]
  parent?: string | null
  type?: MissionType
  priority?: MissionPriority
  reviewer?: number | null
  milestone?: string | null
}

export interface SubmissionSourceInput {
  provider: SubmissionProvider
  repository: string
  revision: string
  browse_url?: string
}

export interface SubmissionBuildInput {
  provider: string
  build_id: string
  platform: string
  source_revision?: string
  artifact_url?: string
  status: BuildStatus
  verification_note?: string
}

export interface SubmitPayload {
  description: string
  verification_description?: string
  source_references?: SubmissionSourceInput[]
  build_references?: SubmissionBuildInput[]
}

/** Only `accept` / `reject` are accepted by the API (legacy `approve` is not). */
export type ReviewDecision = 'accept' | 'reject'

export interface ReviewPayload {
  submission_id: string
  decision: ReviewDecision
  comment?: string
  verified_build_reference_id?: string | null
}

export interface MilestoneCreatePayload {
  name: string
  description?: string
  due_date?: string | null
}

export interface MilestoneUpdatePayload {
  expected_version: number
  name?: string
  description?: string
  due_date?: string | null
}
