/** 本机可选性能采样，不上传用户数据；最多保留 200 条。 */
export type Measurement = { name: 'workspace_reload' | 'gantt_layout'; duration_ms: number; nodes?: number; edges?: number; outcome?: 'ok' | 'error' | 'superseded' }
const samples: Measurement[] = []
const enabled = import.meta.env.VITE_PERFORMANCE_METRICS === '1'
export function recordPerformance(sample: Measurement) {
  if (!enabled) return
  samples.push({ ...sample, duration_ms: Math.round(sample.duration_ms * 1000) / 1000 })
  if (samples.length > 200) samples.shift()
}
export function performanceSnapshot() { return samples.map(sample => ({ ...sample })) }
if (enabled && typeof window !== 'undefined') {
  Object.defineProperty(window, 'mycollabPerformance', { configurable: true, value: {
    snapshot: performanceSnapshot, clear: () => { samples.length = 0 },
  } })
}
