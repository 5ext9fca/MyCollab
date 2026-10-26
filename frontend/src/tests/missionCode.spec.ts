import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import MissionCodePanel from '../components/MissionCodePanel.vue'
import { useAuthStore } from '../stores/auth'
import { listAgentDevices } from '../api/agentBridge'
import { createCodeExecution, getCodeExecution, listCodeExecutions } from '../api/codeExecutions'
import type { CodeExecution } from '../api/codeExecutions'
import type { Mission } from '../api/types'

vi.mock('../api/agentBridge', () => ({ listAgentDevices: vi.fn() }))
vi.mock('../api/codeExecutions', () => ({ createCodeExecution: vi.fn(), getCodeExecution: vi.fn(), listCodeExecutions: vi.fn(), cancelCodeExecution: vi.fn() }))
const user = { id: 1, username: 'owner', display_name: '认领者', is_staff: false }
const mission = { id: 'mission', title: '规则实现', content: '负数归零', acceptance_criteria: '测试覆盖负数', status: 'InProgress', assignee: user, version: 2, assets: [], type: 'Task', priority: 'P2', creator: user, reviewer: user, parent: null, milestone: null, tags: [], created_at: '', updated_at: '', allowed_actions: ['submit'], has_unresolved_prerequisites: false, is_blocked: false, blocking_mission_ids: [], unfinished_child_ids: [], needs_dependency_review: false, reviewer_missing: false, milestone_closed: false } as Mission
const execution: CodeExecution = { id: 'execution', request_id: 'request', mission_id: mission.id, actor_id: 1, mission_version: 2, repository_key: 'demo', version: 1, previous_id: null, status: 'succeeded', manifest: { base_commit: 'a'.repeat(40) }, patch_url: '/api/library/files/file/', stale_reason: '', error: '', expires_at: '2099-01-01', stopped_at: '2026-10-26', created_at: '2026-10-26', published_at: '2026-10-26', report: { schema_version: 1, source: 'local_runner', base_commit: 'a'.repeat(40), summary: '修改规则', changed_files: [{ path: 'rules.py', change: 'modified' }], verification: [{ id: 'unit', label: '单测', status: 'failed', exit_code: 1, duration_ms: 100 }] } }
const wrappers: VueWrapper[] = []
const paginated = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null })
beforeEach(() => {
  setActivePinia(createPinia()); useAuthStore().user = user
  vi.mocked(listAgentDevices).mockResolvedValue(paginated([{ id: 'device', name: '电脑', capabilities: ['code_implement'], expires_at: '2099-01-01', revoked_at: null, last_seen_at: null }]))
  vi.mocked(listCodeExecutions).mockResolvedValue(paginated([]))
  vi.mocked(createCodeExecution).mockResolvedValue({ ...execution, status: 'queued' })
  vi.mocked(getCodeExecution).mockResolvedValue(execution)
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.resetAllMocks() })
async function render(value = mission) {
  const w = mount(MissionCodePanel, { props: { mission: value, canAdopt: true }, global: { plugins: [ElementPlus], stubs: { RouterLink: true } } })
  wrappers.push(w); await flushPromises(); return w
}
async function click(w: VueWrapper, label: string) {
  await w.findAll('button').find(b => b.text() === label)!.trigger('click'); await flushPromises()
}
describe('代码委派人工确认', () => {
  it('预览不执行，确认后网络重发沿用幂等键', async () => {
    const w = await render()
    await w.find('input[placeholder^="例如"]').setValue('demo')
    await w.find('textarea').setValue('实现积分规则')
    await click(w, '预览代码委派')
    expect(createCodeExecution).not.toHaveBeenCalled()
    expect(w.text()).toContain('测试覆盖负数')
    vi.mocked(createCodeExecution).mockRejectedValueOnce(new Error('断线'))
    await click(w, '确认代码委派'); await click(w, '确认代码委派')
    expect(vi.mocked(createCodeExecution).mock.calls[0]![0]).toEqual(vi.mocked(createCodeExecution).mock.calls[1]![0])
    expect(w.emitted('adopt')).toBeUndefined()
  })
  it('仓库字段拒绝本机路径，非认领者不提供委派', async () => {
    const w = await render()
    await w.find('input[placeholder^="例如"]').setValue('/tmp/repo')
    await w.find('textarea').setValue('实现')
    await click(w, '预览代码委派')
    expect(w.text()).toContain('不能是路径或命令')
    await w.setProps({ mission: { ...mission, assignee: { ...user, id: 2 } } })
    expect(w.find('textarea').exists()).toBe(false)
    expect(createCodeExecution).not.toHaveBeenCalled()
  })
  it('待审查只有本地发布提示，没有自动引用或提交', async () => {
    vi.mocked(listCodeExecutions).mockResolvedValue(paginated([{ ...execution, status: 'awaiting_selection', patch_url: null, report: null }]))
    const w = await render()
    expect(w.text()).toContain('--publish-code request')
    expect(w.text()).not.toContain('引用代码成果到提交草稿')
    expect(w.emitted('adopt')).toBeUndefined()
  })
  it('展示失败的本地验证，人工引用前重新检查执行版本', async () => {
    vi.mocked(listCodeExecutions).mockResolvedValue(paginated([execution]))
    const w = await render()
    expect(w.text()).toContain('失败')
    expect(w.text()).toContain('服务器没有运行测试')
    expect(w.emitted('adopt')).toBeUndefined()
    await click(w, '引用代码成果到提交草稿')
    expect(w.emitted('adopt')).toEqual([[execution]])
    vi.mocked(getCodeExecution).mockResolvedValue({ ...execution, status: 'cancelled' })
    await click(w, '引用代码成果到提交草稿')
    expect(w.emitted('adopt')).toHaveLength(1)
    expect(w.text()).toContain('代码成果不可引用')
  })
})
