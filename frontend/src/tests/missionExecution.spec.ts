import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import MissionExecutionPanel from '../components/MissionExecutionPanel.vue'
import { useAuthStore } from '../stores/auth'
import { listAgentDevices } from '../api/agentBridge'
import { getDesignElement } from '../api/designElements'
import { listLibraryFiles } from '../api/library'
import { createExecution, getExecution, listExecutions } from '../api/executions'
import type { MissionExecution } from '../api/executions'
import type { DesignElement, Mission } from '../api/types'

vi.mock('../api/agentBridge', () => ({ listAgentDevices: vi.fn() }))
vi.mock('../api/designElements', () => ({ getDesignElement: vi.fn() }))
vi.mock('../api/library', () => ({ listLibraryFiles: vi.fn() }))
vi.mock('../api/executions', () => ({ createExecution: vi.fn(), getExecution: vi.fn(), listExecutions: vi.fn(), cancelExecution: vi.fn() }))
const user = { id: 1, username: 'owner', display_name: '认领者', is_staff: false }
const asset = { id: 'asset', title: '树叶', kind: 'Asset', archived: false, version: 1, content: '绿色叶片' } as DesignElement
const mission = { id: 'mission', title: '图标', content: '绘制叶片', acceptance_criteria: '白色背景', status: 'InProgress', assignee: user, version: 2, assets: [asset], type: 'Task', priority: 'P2', creator: user, reviewer: user, parent: null, milestone: null, tags: [], created_at: '', updated_at: '', allowed_actions: ['submit'], has_unresolved_prerequisites: false, is_blocked: false, blocking_mission_ids: [], unfinished_child_ids: [], needs_dependency_review: false, reviewer_missing: false, milestone_closed: false } as Mission
const candidate = { id: 'candidate', key: 'candidate_1', name: 'leaf.png', url: '/api/library/files/file/', file_id: 'file', uploaded_at: '2026-10-26', sha256: 'a'.repeat(64), size: 100, width: 2, height: 2 }
const execution: MissionExecution = { id: 'execution', request_id: 'request', mission_id: mission.id, asset_id: asset.id, actor_id: 1, mission_version: 2, asset_version: 1, version: 1, previous_id: null, kind: 'image_generate', status: 'succeeded', selected_ids: ['candidate_1'], candidates: [candidate], stale_reason: '', expires_at: '2099-01-01', error: '', stopped_at: '2026-10-26', created_at: '2026-10-26' }
const wrappers: VueWrapper[] = []
const paginated = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null })
beforeEach(() => {
  setActivePinia(createPinia()); useAuthStore().user = user
  vi.mocked(listAgentDevices).mockResolvedValue(paginated([{ id: 'device', name: '电脑', capabilities: ['image_generate', 'image_edit'], expires_at: '2099-01-01', revoked_at: null, last_seen_at: null }]))
  vi.mocked(getDesignElement).mockResolvedValue(asset)
  vi.mocked(listLibraryFiles).mockResolvedValue(paginated([]))
  vi.mocked(listExecutions).mockResolvedValue(paginated([]))
  vi.mocked(createExecution).mockResolvedValue({ ...execution, status: 'queued' })
  vi.mocked(getExecution).mockResolvedValue(execution)
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.resetAllMocks() })
async function render(value = mission) {
  const w = mount(MissionExecutionPanel, { props: { mission: value, canAdopt: true }, global: { plugins: [ElementPlus], stubs: { RouterLink: true } } })
  wrappers.push(w); await flushPromises(); return w
}
async function click(w: VueWrapper, label: string) {
  await w.findAll('button').find(b => b.text() === label)!.trigger('click'); await flushPromises()
}
describe('Mission 图像委派', () => {
  it('预览不执行，确认委派携带版本，断线重发同一幂等键', async () => {
    const w = await render()
    await w.find('textarea').setValue('制作一张叶片图标')
    await click(w, '预览委派内容')
    expect(createExecution).not.toHaveBeenCalled()
    expect(w.text()).toContain('白色背景')
    vi.mocked(createExecution).mockRejectedValueOnce(new Error('断线'))
    await click(w, '确认委派'); await click(w, '确认委派')
    expect(createExecution).toHaveBeenCalledTimes(2)
    expect(vi.mocked(createExecution).mock.calls[0]![0]).toEqual(vi.mocked(createExecution).mock.calls[1]![0])
    expect(createExecution).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 2, asset_version: 1, device_id: 'device', reference_ids: [] }))
    expect(w.emitted('adopt')).toBeUndefined()
  })
  it('他人或非进行中的 Mission 不提供创建入口', async () => {
    const w = await render({ ...mission, assignee: { ...user, id: 2 } })
    expect(w.find('textarea').exists()).toBe(false)
    await w.setProps({ mission: { ...mission, status: 'Submitted' } })
    expect(w.find('textarea').exists()).toBe(false)
    expect(createExecution).not.toHaveBeenCalled()
  })
  it('未上传候选只显示元数据，不发出引用事件', async () => {
    vi.mocked(listExecutions).mockResolvedValue(paginated([{ ...execution, status: 'awaiting_selection', candidates: [{ ...candidate, file_id: null, url: null }] }]))
    const w = await render()
    expect(w.text()).toContain('仅本地候选')
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).not.toContain('引用到提交草稿')
    expect(w.emitted('adopt')).toBeUndefined()
  })
  it('已上传成果须人工引用，引用前重新核对版本', async () => {
    vi.mocked(listExecutions).mockResolvedValue(paginated([execution]))
    const w = await render()
    expect(w.emitted('adopt')).toBeUndefined()
    await click(w, '引用到提交草稿')
    expect(w.emitted('adopt')).toEqual([[ [candidate] ]])
    vi.mocked(getDesignElement).mockResolvedValue({ ...asset, version: 2 })
    await click(w, '引用到提交草稿')
    expect(w.emitted('adopt')).toHaveLength(1)
    expect(w.text()).toContain('资产已变化')
  })
  it('只提供设备声明的图像操作，编辑必须选择参考图', async () => {
    vi.mocked(listAgentDevices).mockResolvedValue(paginated([{ id: 'edit-device', name: '编辑设备', capabilities: ['image_edit'], expires_at: '2099-01-01', revoked_at: null, last_seen_at: null }]))
    const w = await render()
    expect(w.text()).not.toContain('生成图片')
    expect(w.text()).toContain('编辑参考图')
    await w.find('textarea').setValue('修改颜色')
    await click(w, '预览委派内容')
    expect(w.text()).toContain('编辑至少选择 1 张')
    expect(createExecution).not.toHaveBeenCalled()
  })
  it('没有未归档资产时保留历史但不提供创建表单', async () => {
    const w = await render({ ...mission, assets: [] })
    expect(w.find('textarea').exists()).toBe(false)
    expect(w.text()).toContain('请先为 Mission 关联未归档的 Asset')
  })

})
