/** Shared label maps and select options for the mission domain enums. */
import type {
  BuildStatus,
  MilestoneStatus,
  MissionPriority,
  MissionStatus,
  MissionType,
  SubmissionOutcome,
  SubmissionProvider,
} from './api/types'

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

export const STATUS_OPTIONS: { label: string; value: MissionStatus }[] = [
  { label: '待认领', value: 'Open' },
  { label: '进行中', value: 'InProgress' },
  { label: '待验收', value: 'Submitted' },
  { label: '已完成', value: 'Done' },
  { label: '已取消', value: 'Cancelled' },
]

export const STATUS_LABELS: Record<MissionStatus, string> = {
  Open: '待认领',
  InProgress: '进行中',
  Submitted: '待验收',
  Done: '已完成',
  Cancelled: '已取消',
}

export const TYPE_OPTIONS: { label: string; value: MissionType }[] = [
  { label: '功能（Feature）', value: 'Feature' },
  { label: '任务（Task）', value: 'Task' },
  { label: '缺陷（Bug）', value: 'Bug' },
]

export const TYPE_LABELS: Record<MissionType, string> = {
  Feature: '功能',
  Task: '任务',
  Bug: '缺陷',
}

export const TYPE_TAG: Record<MissionType, TagType> = {
  Feature: 'primary',
  Task: 'info',
  Bug: 'danger',
}

export const PRIORITY_OPTIONS: { label: string; value: MissionPriority }[] = [
  { label: 'P0 紧急阻断', value: 'P0' },
  { label: 'P1 重要', value: 'P1' },
  { label: 'P2 普通', value: 'P2' },
  { label: 'P3 可延期', value: 'P3' },
]

export const PRIORITY_LABELS: Record<MissionPriority, string> = {
  P0: 'P0',
  P1: 'P1',
  P2: 'P2',
  P3: 'P3',
}

export const PRIORITY_TAG: Record<MissionPriority, TagType> = {
  P0: 'danger',
  P1: 'warning',
  P2: 'info',
  P3: 'info',
}

export const MILESTONE_STATUS_LABELS: Record<MilestoneStatus, string> = {
  Planned: '计划中',
  Active: '进行中',
  Completed: '已完成',
  Cancelled: '已取消',
}

export const MILESTONE_STATUS_TAG: Record<MilestoneStatus, TagType> = {
  Planned: 'info',
  Active: 'primary',
  Completed: 'success',
  Cancelled: 'danger',
}

/** Milestones in these states can receive new or reassigned missions. */
export const MILESTONE_ACCEPTING_STATUSES: MilestoneStatus[] = ['Planned', 'Active']

export const SUBMISSION_OUTCOME_LABELS: Record<SubmissionOutcome, string> = {
  Pending: '待验收',
  Accepted: '已通过',
  Rejected: '已退回',
}

export const SUBMISSION_OUTCOME_TAG: Record<SubmissionOutcome, TagType> = {
  Pending: 'warning',
  Accepted: 'success',
  Rejected: 'danger',
}

export const BUILD_STATUS_LABELS: Record<BuildStatus, string> = {
  Unknown: '未知',
  Pending: '等待中',
  Succeeded: '成功',
  Failed: '失败',
}

export const BUILD_STATUS_TAG: Record<BuildStatus, TagType> = {
  Unknown: 'info',
  Pending: 'warning',
  Succeeded: 'success',
  Failed: 'danger',
}

export const BUILD_STATUS_OPTIONS: { label: string; value: BuildStatus }[] = [
  { label: '成功', value: 'Succeeded' },
  { label: '等待中', value: 'Pending' },
  { label: '失败', value: 'Failed' },
  { label: '未知', value: 'Unknown' },
]

export const SOURCE_PROVIDER_OPTIONS: { label: string; value: SubmissionProvider }[] = [
  { label: 'Git', value: 'Git' },
  { label: 'Perforce', value: 'Perforce' },
  { label: 'UVCS（Unity Version Control）', value: 'UVCS' },
  { label: '其他', value: 'Other' },
]
