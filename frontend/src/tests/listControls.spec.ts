import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import MissionListSection from '../components/MissionListSection.vue'
import NotificationsView from '../views/NotificationsView.vue'
import BulkMissionEditor from '../components/BulkMissionEditor.vue'
import { listMissions } from '../api/missions'
import { listNotifications, readNotifications } from '../api/notifications'
import type { Mission } from '../api/types'
vi.mock('../api/missions', () => ({ listMissions: vi.fn(), bulkUpdateMissions: vi.fn(), getMission: vi.fn() }))
vi.mock('../api/notifications', () => ({ listNotifications: vi.fn(), readNotifications: vi.fn(), notifyChanged: vi.fn() }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; vi.clearAllMocks() })
describe('列表控制', () => {
  it('个人列表固定范围，筛选与每页条数改变时回到首页并清空选择', async () => {
    vi.mocked(listMissions).mockResolvedValue({ count: 80, results: [{ id: 'a', title: '任务' }] as Mission[], next: null, previous: null })
    const wrapper = mount(MissionListSection, { props: { title: '我发布的', query: { creator: 'me' } }, global: { plugins: [ElementPlus], stubs: { MissionQuickFilters: true, MissionCard: { template: '<div><slot name="selection" /></div>' }, BulkMissionEditor: true } } }); wrappers.push(wrapper)
    await flushPromises()
    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    pagination.vm.$emit('current-change', 3); await flushPromises()
    expect(listMissions).toHaveBeenLastCalledWith(expect.objectContaining({ creator: 'me', page: 3 }))
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.findComponent(BulkMissionEditor).props('selectedIds')).toEqual(['a'])
    pagination.vm.$emit('size-change', 50); await flushPromises()
    expect(listMissions).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 50 }))
    expect(wrapper.findComponent(BulkMissionEditor).props('selectedIds')).toEqual([])
    wrapper.findComponent({ name: 'MissionQuickFilters' }).vm.$emit('apply', { creator: 'other', status: 'Done', ordering: 'title' }); await flushPromises()
    expect(listMissions).toHaveBeenLastCalledWith(expect.objectContaining({ creator: 'me', status: 'Done', ordering: 'title', page: 1 }))
  })
  it('任务本页全选支持半选、取消全选与切页清空', async () => {
    const wrapper = mount(BulkMissionEditor, { props: { missions: [{ id: 'a' }, { id: 'b' }] as Mission[], selectedIds: ['a'], resetKey: '1' }, global: { plugins: [ElementPlus] } }); wrappers.push(wrapper)
    expect(wrapper.findComponent({ name: 'ElCheckbox' }).props('indeterminate')).toBe(true)
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.emitted('update:selectedIds')?.at(-1)).toEqual([['a', 'b']])
    await wrapper.setProps({ selectedIds: ['a', 'b'] })
    await wrapper.get('input[type="checkbox"]').setValue(false)
    expect(wrapper.emitted('update:selectedIds')?.at(-1)).toEqual([[]])
    await wrapper.setProps({ resetKey: '2' })
    expect(wrapper.emitted('update:selectedIds')?.at(-1)).toEqual([[]])
  })
  it('通知全选不会标已读，排序与页长传至服务端并清空选择', async () => {
    vi.mocked(listNotifications).mockResolvedValue({ count: 2, results: ['a', 'b'].map(id => ({ id, mission_title: id, payload: {}, created_at: '2026-10-25' })) as never, next: null, previous: null })
    const wrapper = mount(NotificationsView, { global: { plugins: [ElementPlus], stubs: { MissionDetailDrawer: true } } }); wrappers.push(wrapper)
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.findComponent({ name: 'ElCheckboxGroup' }).props('modelValue')).toEqual(['a', 'b'])
    expect(readNotifications).not.toHaveBeenCalled()
    wrapper.findAllComponents({ name: 'ElSelect' })[1]!.vm.$emit('update:modelValue', 'created_at'); await flushPromises()
    expect(wrapper.findComponent({ name: 'ElCheckboxGroup' }).props('modelValue')).toEqual([])
    wrapper.findComponent({ name: 'ElPagination' }).vm.$emit('size-change', 10); await flushPromises()
    expect(listNotifications).toHaveBeenLastCalledWith({ read: 'all', ordering: 'created_at', page: 1, page_size: 10 })
  })
})
