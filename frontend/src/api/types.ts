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
  /** Only present on the F5 workspace milestone briefs. */
  overdue?: boolean
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

export interface Mission extends ScheduleFields {
  design_element?: DesignElementBrief | null
  assets?: DesignElementBrief[]
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
  execution_artifacts?: { candidate_id: string; execution_id: string; asset_id: string; version: number; name: string; sha256: string; url: string }[]
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
  planned_start_date?: string | null
  planned_end_date?: string | null
  design_element_id?: string | null
  asset_ids?: string[]
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
  planned_start_date?: string | null
  planned_end_date?: string | null
  design_element_id?: string | null
  asset_ids?: string[]
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
  planned_start_date?: string | null
  planned_end_date?: string | null
  design_element_id?: string | null
  asset_ids?: string[]
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
  execution_candidate_ids?: string[]
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

/* -------------------------------------------------------------------------
 * F5 workspace (milestone board + dependency graph)
 * ----------------------------------------------------------------------- */

export type WorkspaceScope = 'team' | 'milestone' | 'mission'
export type WorkspaceExpand = 'none' | 'one' | 'all'
export type WorkspaceDirection = 'upstream' | 'downstream' | 'both'

/** One mission as rendered on the board and in the graph. */
export interface WorkspaceNode extends ScheduleFields {
  milestone_due_date?: string | null
  unloaded_prerequisite_count?: number
  id: string
  title: string
  type: MissionType
  priority: MissionPriority
  status: MissionStatus
  creator: User
  assignee: User | null
  reviewer: User | null
  parent_id: string | null
  milestone_id: string | null
  milestone_name: string | null
  version: number
  created_at: string
  updated_at: string
  is_blocked: boolean
  has_unresolved_prerequisites: boolean
  /** Done but its prerequisites are no longer satisfied (F1 review hint). */
  requires_revalidation: boolean
  needs_dependency_review: boolean
  blocking_count: number
  unfinished_child_count: number
  reviewer_missing: boolean
  milestone_closed: boolean
  /** Visible for context but excluded by the active task filters. */
  is_context: boolean
  allowed_actions: string[]
}

export interface WorkspaceEdge {
  id: string
  mission_id: string
  prerequisite_id: string
  is_satisfied: boolean
  cross_milestone: boolean
}

/** `parent -> child` decomposition edge; never a dependency edge. */
export interface WorkspaceParentEdge {
  child_id: string
  parent_id: string
}

export interface WorkspaceGroup {
  milestone: MilestoneBrief | null
  is_unassigned: boolean
  /** Full visible scope of the milestone (ignores task filters). */
  full_counts: MilestoneCounts
  /** Declares that `full_counts` covers every visible mission of the milestone. */
  full_counts_scope: 'milestone_all_visible'
  /** Matched counts per status under the active filters. */
  matched_counts: Record<MissionStatus, number>
  /** Declares that `matched_counts` is narrowed by the active filters. */
  matched_counts_scope: 'active_filters'
  matched_total: number
  loaded: Record<MissionStatus, number>
  columns: Record<MissionStatus, WorkspaceNode[]>
}

export interface WorkspaceSummary {
  matched_total: number
  effective_total: number
  done: number
  blocked: number
  submitted: number
  requires_revalidation: number
}

export interface WorkspaceOverview {
  generated_at: string
  /** Stable read-snapshot id (not a per-request random value). */
  revision: string
  filters_active: boolean
  column_limit: number
  columns: MissionStatus[]
  column_labels: Record<MissionStatus, string>
  summary: WorkspaceSummary
  groups: WorkspaceGroup[]
}

export interface WorkspaceGraphMeta {
  date_from?: string
  date_to?: string
  today?: string
  scope: WorkspaceScope
  focus: string | null
  expand: WorkspaceExpand
  direction: WorkspaceDirection
  depth: number
  matched_count: number
  matched_included: number
  context_count: number
  node_count: number
  edge_count: number
  parent_edge_count: number
  node_limit: number
  edge_limit: number
  context_limit: number
  nodes_truncated: boolean
  context_truncated: boolean
  edges_truncated: boolean
  /** Any relation was dropped for hitting a server-side budget. */
  truncated: boolean
  truncation_reasons: string[]
  /** False when any node/context/edge budget cut the response short. */
  relationships_complete: boolean
}

export interface WorkspaceGraph {
  generated_at: string
  /** Stable read-snapshot id shared with the overview when rows are unchanged. */
  revision: string
  filters_active: boolean
  nodes: WorkspaceNode[]
  edges: WorkspaceEdge[]
  parent_edges: WorkspaceParentEdge[]
  meta: WorkspaceGraphMeta
}


export interface DesignElementBrief {
  id: string
  title: string
  kind: 'Design' | 'Asset'
  archived: boolean
}
export interface DesignElement extends DesignElementBrief {
  content: string
  parent: DesignElementBrief | null
  ancestors: DesignElementBrief[]
  assets: DesignElementBrief[]
  referencing_designs: DesignElementBrief[]
  prerequisites: DesignElementBrief[]
  dependents: DesignElementBrief[]
  created_by: User
  version: number
  created_at: string
  updated_at: string
  allowed_actions: string[]
  has_children: boolean
  progress: { effective_total: number; done: number; progress: number | null; blocked: number; revalidation: number }
}
export interface DesignInput {
  prerequisite_ids?: string[]
  asset_ids?: string[]
  title: string
  content: string
  kind: 'Design' | 'Asset'
  parent: string | null
}

export interface ProductionStep {
  key: string
  title: string
  content: string
  acceptance_criteria: string
  type: MissionType
  priority: MissionPriority
  tags: string[]
  prerequisite_keys: string[]
}
export interface ProductionTemplate {
  id: string
  name: string
  description: string
  steps: ProductionStep[]
  created_by: User
  version: number
  archived: boolean
  created_at: string
  updated_at: string
  allowed_actions: string[]
}
export interface ProductionData {
  batch: { id: string; template_id: string; template_version: number; template_snapshot: { name: string; steps: ProductionStep[] }; created_at: string } | null
  items: { step_key: string; mission: Mission }[]
}


export interface ScheduleFields {
  planned_start_date?: string | null
  planned_end_date?: string | null
  overdue?: boolean
  dependency_date_conflict_ids?: string[]
  beyond_milestone_due?: boolean
}
