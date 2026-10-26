import { flushPromises, mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import MyWorkView from '../views/MyWorkView.vue'
import NotificationsView from '../views/NotificationsView.vue'
import * as api from '../api/notifications'
vi.mock('../api/notifications', () => ({ workMissions: vi.fn(), workSummary: vi.fn(), listNotifications: vi.fn(), readNotifications: vi.fn(), notifyChanged: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn() } }))
const global = { stubs: { MissionQuickFilters: true, BulkMissionEditor: true, MissionCard: { props: ['mission'], template: '<p>{{ mission.title }}</p>' }, MissionDetailDrawer: true, ElButton: { template: '<button><slot /></button>' }, ElPagination: true, ElEmpty: true, ElSelect: true, ElCheckboxGroup: { template: '<div><slot /></div>' }, ElCheckbox: true }, directives: { loading: () => {} } }
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.workSummary).mockResolvedValue({ today: '2026-10-25', counts: {} as never, unread_notification_count: 0 }) })
describe('个人工作与收件箱', () => {
  it('切换分类后旧请求不能覆盖新结果，详情动作刷新待办', async () => {
    let resolveOld!: (value: never) => void
    vi.mocked(api.workMissions).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockResolvedValue({ results: [{ id: 'b', title: '新分类' }] as never, count: 1, next: null, previous: null })
    const wrapper = mount(MyWorkView, { global })
    await wrapper.findAll('button')[1]!.trigger('click'); await flushPromises()
    resolveOld({ results: [{ id: 'a', title: '旧分类' }], count: 1 } as never); await flushPromises()
    expect(wrapper.text()).toContain('新分类'); expect(wrapper.text()).not.toContain('旧分类')
    wrapper.findComponent({ name: 'MissionDetailDrawer' }).vm.$emit('changed'); await flushPromises()
    expect(api.workSummary).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('仅浏览通知不标已读，标记失败不打开任务', async () => {
    vi.mocked(api.listNotifications).mockResolvedValue({ results: [{ id: 'n', mission: 'm', mission_title: '任务', payload: { summary: '消息' }, read_at: null, created_at: '2026-10-25' }] as never, count: 1, next: null, previous: null })
    vi.mocked(api.readNotifications).mockRejectedValue(new Error('失败'))
    const wrapper = mount(NotificationsView, { global }); await flushPromises()
    expect(api.readNotifications).not.toHaveBeenCalled()
    await wrapper.findAll('button')[1]!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('未读')
    expect(api.notifyChanged).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
