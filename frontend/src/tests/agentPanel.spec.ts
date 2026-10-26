import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import AgentPanel from '../components/AgentPanel.vue'
import MissionCodePanel from '../components/MissionCodePanel.vue'
import MissionExecutionPanel from '../components/MissionExecutionPanel.vue'
import { useAuthStore } from '../stores/auth'
import { listAgentDevices } from '../api/agentBridge'
import { listCodeExecutions } from '../api/codeExecutions'
import { listExecutions } from '../api/executions'
import { listLibraryFiles } from '../api/library'
import type { CodeExecution } from '../api/codeExecutions'
import type { Mission } from '../api/types'
vi.mock('../api/agentBridge', () => ({ listAgentDevices: vi.fn() }))
vi.mock('../api/codeExecutions', () => ({ listCodeExecutions: vi.fn() }))
vi.mock('../api/executions', () => ({ listExecutions: vi.fn() }))
vi.mock('../api/library', () => ({ listLibraryFiles: vi.fn() }))
const user = { id: 1, username: 'owner', display_name: '认领者', is_staff: false }
const mission = { id: 'mission', title: '规则实现', content: '负数归零', acceptance_criteria: '测试覆盖负数', status: 'InProgress', assignee: user, version: 2, assets: [], type: 'Task', priority: 'P2', creator: user, reviewer: user, parent: null, milestone: null, tags: [], created_at: '', updated_at: '', allowed_actions: ['submit'], has_unresolved_prerequisites: false, is_blocked: false, blocking_mission_ids: [], unfinished_child_ids: [], needs_dependency_review: false, reviewer_missing: false, milestone_closed: false } as Mission
const execution: CodeExecution = { id: 'execution', request_id: 'request', mission_id: mission.id, actor_id: 1, mission_version: 2, repository_key: 'demo', version: 1, previous_id: null, status: 'succeeded', manifest: { base_commit: 'a'.repeat(40) }, patch_url: '/api/library/files/file/', stale_reason: '', error: '', expires_at: '2099-01-01', stopped_at: '2026-10-26', created_at: '2026-10-26', published_at: '2026-10-26', report: { schema_version: 1, source: 'local_runner', base_commit: 'a'.repeat(40), summary: '修改规则', changed_files: [{ path: 'rules.py', change: 'modified' }], verification: [{ id: 'unit', label: '单测', status: 'failed', exit_code: 1, duration_ms: 100 }] } }

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null })
let wrapper: VueWrapper
beforeEach(() => {
  vi.useFakeTimers()
  setActivePinia(createPinia()); useAuthStore().user = user
  vi.mocked(listAgentDevices).mockResolvedValue(page([]))
  vi.mocked(listCodeExecutions).mockResolvedValue(page([{ ...execution, status: 'running' }]))
  vi.mocked(listExecutions).mockResolvedValue(page([]))
  vi.mocked(listLibraryFiles).mockResolvedValue(page([]))
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.resetAllMocks() })
async function render() {
  wrapper = mount(AgentPanel, { props: { mission, canAdopt: true }, global: { plugins: [ElementPlus], stubs: { RouterLink: true } } })
  await flushPromises()
}
describe('统一 Agent 面板', () => {
  it('原委托位置仅保留记录和成果引用，不加载设备或挂载交互操作', async () => {
    wrapper = mount(AgentPanel, { props: { mission, canAdopt: true, recordsOnly: true }, global: { plugins: [ElementPlus], stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('Agent 交互记录')
    expect(wrapper.text()).not.toContain('创建代码委派')
    expect(wrapper.text()).not.toContain('私有对话与权限审批')
    expect(wrapper.text()).not.toContain('取消代码执行')
    expect(listAgentDevices).not.toHaveBeenCalled()
    wrapper.findComponent(MissionCodePanel).vm.$emit('adopt', execution)
    expect(wrapper.emitted('adoptCode')).toEqual([[execution]])
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true)
    await flushPromises()
    expect(wrapper.text()).not.toContain('创建图像委派')
    expect(listLibraryFiles).not.toHaveBeenCalled()
    expect(listAgentDevices).not.toHaveBeenCalled()
  })
  it('类型切换只挂载一类，停止旧轮询；重新打开读取当前记录', async () => {
    await render()
    expect(listCodeExecutions).toHaveBeenCalledTimes(1)
    expect(listExecutions).not.toHaveBeenCalled()
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true)
    await flushPromises()
    expect(wrapper.findComponent(MissionCodePanel).exists()).toBe(false)
    expect(listExecutions).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60000)
    expect(listCodeExecutions).toHaveBeenCalledTimes(1)
    expect(listExecutions).toHaveBeenCalledTimes(1)
    await wrapper.findAll('input[type="radio"]')[0]!.setValue(true)
    await flushPromises()
    expect(listCodeExecutions).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(60000)
    expect(listCodeExecutions).toHaveBeenCalledTimes(2)
  })
  it('读取失败按退避重试，终态停止轮询', async () => {
    vi.mocked(listCodeExecutions).mockRejectedValueOnce(new Error('网络断开')).mockRejectedValueOnce(new Error('网络断开')).mockResolvedValue(page([execution]))
    await render()
    await vi.advanceTimersByTimeAsync(15000)
    expect(listCodeExecutions).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(29000)
    expect(listCodeExecutions).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1000)
    expect(listCodeExecutions).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(60000)
    expect(listCodeExecutions).toHaveBeenCalledTimes(3)
  })
  it('迟到的旧 Mission 响应不会覆盖新记录或重启旧轮询', async () => {
    let resolve!: (value: ReturnType<typeof page<CodeExecution>>) => void
    vi.mocked(listCodeExecutions).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    await render()
    await wrapper.setProps({ mission: { ...mission, id: 'next' } })
    await flushPromises()
    resolve(page([{ ...execution, repository_key: '旧记录' }]))
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧记录')
    await vi.advanceTimersByTimeAsync(15000)
    expect(listCodeExecutions).toHaveBeenLastCalledWith('next', 1)
    expect(listCodeExecutions).toHaveBeenCalledTimes(3)
  })
  it('只转发对应成果事件，未具备能力时隐藏创建表单并保留历史', async () => {
    await render()
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无声明代码实现能力')
    wrapper.findComponent(MissionCodePanel).vm.$emit('adopt', execution)
    expect(wrapper.emitted('adoptCode')).toEqual([[execution]])
    expect(wrapper.emitted('adoptImages')).toBeUndefined()
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true)
    await flushPromises()
    wrapper.findComponent(MissionExecutionPanel).vm.$emit('adopt', [])
    expect(wrapper.emitted('adoptImages')).toEqual([[[]]])
  })
})
