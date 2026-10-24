import { describe, expect, it } from 'vitest'
import { computeGanttLayout } from '../composables/useGanttLayout'
import type { WorkspaceNode } from '../api/types'
function node(id: string, start: string | null, end: string | null): WorkspaceNode {
  return { id, planned_start_date: start, planned_end_date: end } as WorkspaceNode
}
describe('甘特日期投影', () => {
  it('横轴映射真实日期，缺一端不推算时长，未排期单列区域', () => {
    const nodes = [node('a', '2026-10-01', '2026-10-03'), node('b', '2026-10-03', '2026-10-06'), node('c', null, '2026-10-10'), node('d', null, null)]
    const result = computeGanttLayout(nodes, [], null, '2026-10-01', '2026-10-31', 'day')
    expect(result.bars.get('a')!.width).toBe(96)
    expect(result.positions.get('b')!.x - result.positions.get('a')!.x).toBe(64)
    expect(result.bars.get('c')!.width).toBe(32)
    expect(result.bars.get('c')!.label).toContain('未设开始')
    expect(result.bars.get('d')!.unscheduled).toBe(true)
    expect(result.positions.get('d')!.y).toBeGreaterThan(result.positions.get('c')!.y)
  })
  it('裁剪窗口只影响展示，不修改日期，日周缩放与状态更新保持语义', () => {
    const nodes = [node('a', '2026-09-25', '2026-11-02')]
    const day = computeGanttLayout(nodes, [], null, '2026-10-01', '2026-10-31', 'day')
    const week = computeGanttLayout(nodes, [], null, '2026-10-01', '2026-10-31', 'week')
    expect(day.bars.get('a')!.clippedStart).toBe(true); expect(day.bars.get('a')!.clippedEnd).toBe(true)
    expect(day.bars.get('a')!.width).toBe(31 * 32); expect(week.bars.get('a')!.width).toBe(31 * 14)
    expect(nodes[0]!.planned_end_date).toBe('2026-11-02')
    expect(computeGanttLayout([{ ...nodes[0]!, status: 'Done' }], [], null, '2026-10-01', '2026-10-31', 'day').positions).toEqual(day.positions)
  })
})
