import { recordPerformance } from '../performance'
/** 甘特图的纯日期坐标：不推算缺失日期，不改变业务排期。 */
import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import type { GroupInfo } from '../workspace/dto'
import { dependencyLevels } from './useGraphLayout'

export const GANTT_ROW_HEIGHT = 164
export const GANTT_ORIGIN = 280
export const GANTT_FIRST_ROW = 190
const DAY = 86_400_000
export const dayNumber = (value: string) => Date.parse(`${value}T00:00:00Z`) / DAY
export const isoDay = (value: number) => new Date(value * DAY).toISOString().slice(0, 10)
export interface GanttBar {
  width: number
  label: string
  unscheduled: boolean
  incomplete: boolean
  clippedStart: boolean
  clippedEnd: boolean
}
export function computeGanttLayout(nodes: WorkspaceNode[], edges: WorkspaceEdge[], grouping: GroupInfo | null, from: string, to: string, zoom: 'day' | 'week') {
  const measuredAt = performance.now()
  const start = dayNumber(from), end = dayNumber(to)
  const scale = zoom === 'day' ? 32 : 14
  const levels = dependencyLevels(nodes.map(n => n.id), edges).levels
  const ordered = grouping ? [...nodes] : [...nodes].sort((a, b) => (levels.get(a.id) ?? 0) - (levels.get(b.id) ?? 0) || a.id.localeCompare(b.id))
  const dated = ordered.filter(n => n.planned_start_date || n.planned_end_date)
  const undated = ordered.filter(n => !n.planned_start_date && !n.planned_end_date)
  const rows = [...dated, ...undated]
  const positions = new Map<string, { x: number; y: number }>()
  const bars = new Map<string, GanttBar>()
  rows.forEach((node, index) => {
    const first = node.planned_start_date, last = node.planned_end_date
    const unscheduled = !first && !last
    const a = first || last ? dayNumber((first || last)!) : start
    const b = last || first ? dayNumber((last || first)!) : start
    const left = Math.max(start, Math.min(end, a)), right = Math.max(start, Math.min(end, b))
    positions.set(node.id, { x: GANTT_ORIGIN + (left - start) * scale, y: GANTT_FIRST_ROW + index * GANTT_ROW_HEIGHT + (unscheduled ? 36 : 0) })
    bars.set(node.id, { width: unscheduled ? 220 : first && last ? Math.max(scale, (right - left + 1) * scale) : scale,
      unscheduled, incomplete: !first || !last, clippedStart: a < start, clippedEnd: b > end,
      label: unscheduled ? '未排期' : `${a < start ? '← 延伸 ' : ''}${first ?? '未设开始'} → ${last ?? '未设结束'}${b > end ? ' 延伸 →' : ''}` })
  })
  recordPerformance({ name: 'gantt_layout', duration_ms: performance.now() - measuredAt, nodes: nodes.length, edges: edges.length })
  return { positions, bars, rows, scale, days: end - start + 1, width: (end - start + 1) * scale,
    height: GANTT_FIRST_ROW + rows.length * GANTT_ROW_HEIGHT + 50,
    undatedY: undated.length ? GANTT_FIRST_ROW + dated.length * GANTT_ROW_HEIGHT - 115 : null }
}
