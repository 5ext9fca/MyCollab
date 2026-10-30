import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })
it('仅显式开启时记录，样本有界且快照不可修改原数据', async () => {
  vi.stubEnv('VITE_PERFORMANCE_METRICS', '1')
  const { recordPerformance, performanceSnapshot } = await import('../performance')
  for (let i = 0; i < 205; i++) recordPerformance({ name: 'gantt_layout', duration_ms: i, nodes: i })
  const result = performanceSnapshot()
  expect(result).toHaveLength(200)
  expect(result[0]?.nodes).toBe(5)
  result[0]!.nodes = 999
  expect(performanceSnapshot()[0]?.nodes).toBe(5)
})
it('默认不记录', async () => {
  vi.stubEnv('VITE_PERFORMANCE_METRICS', '')
  const { recordPerformance, performanceSnapshot } = await import('../performance')
  recordPerformance({ name: 'workspace_reload', duration_ms: 10 })
  expect(performanceSnapshot()).toEqual([])
})
