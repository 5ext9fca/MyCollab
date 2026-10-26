import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'
import MissionDetailView from '../views/MissionDetailView.vue'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
import * as api from '../api/missions'
import type { Mission, MissionSubmission } from '../api/types'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() }, ElMessageBox: {} }))
vi.mock('../api/auth', () => ({ listTeamMembers: vi.fn().mockResolvedValue([]) }))
vi.mock('../api/comments', () => ({ listComments: vi.fn().mockResolvedValue({ results: [], count: 0 }) }))
vi.mock('../api/missions', () => ({ getMission: vi.fn(), listEvents: vi.fn(), listDependencies: vi.fn(), listSubmissions: vi.fn(), reviewMission: vi.fn() }))
const user = { id: 1, username: 'reviewer', display_name: '验收者' }
let mission: Mission
let submission: MissionSubmission
const wrappers: VueWrapper[] = []
const global = {
  renderStubDefaultSlot: true,
  directives: { loading: () => {} },
  stubs: {
    ElButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
    ElDialog: { props: ['modelValue'], template: '<section v-if="modelValue" class="dialog"><slot /><slot name="footer" /></section>' },
    MarkdownEditor: { props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  },
}
async function setup() {
  const wrapper = shallowMount(MissionDetailView, { props: { id: mission.id }, global })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
async function click(wrapper: VueWrapper, label: string) {
  const button = wrapper.findAll('button').find(item => item.text() === label)
  expect(button, `应显示 ${label}`).toBeDefined()
  await button!.trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  mission = {
    id: 'mission-1', title: '待验收任务', status: 'Submitted', type: 'Task', priority: 'P2',
    creator: user, assignee: user, reviewer: user, parent: null, milestone: null, tags: [], version: 7,
    created_at: '2026-10-26', updated_at: '2026-10-26', allowed_actions: ['review', 'transfer_review'],
    has_unresolved_prerequisites: false, is_blocked: false, blocking_mission_ids: [], unfinished_child_ids: [],
    needs_dependency_review: false, reviewer_missing: false, milestone_closed: false, current_submission: 'submission-1',
  }
  submission = {
    id: 'submission-1', mission: mission.id, submitted_by: user, submitted_at: '2026-10-26',
    description: '本轮成果', verification_description: '检查说明', reviewer_snapshot: user, outcome: 'Pending',
    reviewed_by: null, reviewed_at: null, review_comment: '', verified_build_reference: null,
    source_references: [], build_references: [],
  }
  vi.mocked(api.getMission).mockImplementation(async () => mission)
  vi.mocked(api.listEvents).mockResolvedValue({ results: [], count: 0, next: null, previous: null })
  vi.mocked(api.listDependencies).mockResolvedValue({ prerequisites: [], dependents: [], has_unresolved_prerequisites: false })
  vi.mocked(api.listSubmissions).mockImplementation(async () => ({ results: [submission], count: 1, next: null, previous: null }))
  vi.mocked(api.reviewMission).mockImplementation(async () => ({ ...mission, status: 'InProgress', allowed_actions: [] }))
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })

describe('完整任务详情的验收操作', () => {
  it('退回要求意见，携带当前成果与版本，成功后刷新记录并关闭弹窗', async () => {
    const wrapper = await setup()
    await click(wrapper, '退回')
    await click(wrapper, '确认退回')
    expect(api.reviewMission).not.toHaveBeenCalled()
    expect(ElMessage.warning).toHaveBeenCalledWith('退回时必须填写验收意见')
    await wrapper.find('.dialog textarea').setValue('请补充重开规则')
    await click(wrapper, '确认退回')
    expect(api.reviewMission).toHaveBeenCalledWith('mission-1', {
      submission_id: 'submission-1', decision: 'reject', comment: '请补充重开规则', verified_build_reference_id: null,
    }, 7)
    expect(api.listSubmissions).toHaveBeenCalledTimes(2)
    expect(api.listEvents).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.dialog').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'StatusTag' }).props('status')).toBe('InProgress')
  })
  it('失败构建与依赖阻塞不阻止退回，但失败构建不能验收通过', async () => {
    mission.is_blocked = true
    submission.build_references = [{ id: 'build-1', provider: 'Other', build_id: 'failed-build', platform: 'Windows', source_revision: '', artifact_url: '', status: 'Failed', verification_note: '' }]
    const wrapper = await setup()
    await click(wrapper, '验收')
    expect(wrapper.findAll('button').find(item => item.text() === '确认通过')!.attributes('disabled')).toBeDefined()
    await wrapper.find('.dialog button').trigger('click')
    await click(wrapper, '退回')
    await wrapper.find('.dialog textarea').setValue('修复构建后重新提交')
    await click(wrapper, '确认退回')
    expect(api.reviewMission).toHaveBeenCalledWith(mission.id, expect.objectContaining({ decision: 'reject' }), 7)
  })
  it('人工验收通过仍要求说明并提交 accept', async () => {
    const wrapper = await setup()
    await click(wrapper, '验收')
    await click(wrapper, '确认通过')
    expect(api.reviewMission).not.toHaveBeenCalled()
    await wrapper.find('.dialog textarea').setValue('逐项核对规则，符合标准')
    await click(wrapper, '确认通过')
    expect(api.reviewMission).toHaveBeenCalledWith(mission.id, expect.objectContaining({ decision: 'accept', comment: '逐项核对规则，符合标准' }), 7)
  })
  it('无验收权限时不提供通过或退回入口', async () => {
    mission.allowed_actions = []
    const wrapper = await setup()
    const labels = wrapper.findAll('.detail-actions button').map(item => item.text())
    expect(labels).not.toContain('验收')
    expect(labels).not.toContain('退回')
  })
  it.each([
    { actions: ['claim', 'cancel'] }, { actions: ['release', 'cancel'] },
    { actions: ['review', 'transfer_review'] }, { actions: ['reopen'] },
  ])('详情页包含抽屉授权的任务动作 $actions', async ({ actions }) => {
    mission.allowed_actions = actions
    const detail = await setup()
    const drawer = shallowMount(MissionDetailDrawer, { props: { missionId: mission.id, open: true }, global })
    wrappers.push(drawer)
    await flushPromises()
    const detailLabels = detail.findAll('.detail-actions button').map(item => item.text())
    const drawerLabels = drawer.findAll('.drawer__actions button').map(item => item.text()).filter(label => label !== '完整详情页')
    expect(drawerLabels.length).toBeGreaterThan(0)
    for (const label of drawerLabels) expect(detailLabels).toContain(label)
  })
})
