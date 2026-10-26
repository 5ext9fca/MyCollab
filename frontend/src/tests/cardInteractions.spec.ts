import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { defineComponent, ref } from 'vue'
import MissionCard from '../components/MissionCard.vue'
import NotificationsView from '../views/NotificationsView.vue'
import DesignNavigation from '../components/DesignNavigation.vue'
import DesignTreeBranch from '../components/DesignTreeBranch.vue'
import { listNotifications, readNotifications } from '../api/notifications'
import { listDesignElements } from '../api/designElements'
import type { Mission } from '../api/types'

vi.mock('../api/notifications', () => ({ listNotifications: vi.fn(), readNotifications: vi.fn(), notifyChanged: vi.fn() }))
vi.mock('../api/designElements', () => ({ listDesignElements: vi.fn() }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; vi.clearAllMocks() })
async function router() {
  const result = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/design/:id?', name: 'design', component: { template: '<div />' } },
    { path: '/templates', name: 'production-templates', component: { template: '<div />' } },
  ] })
  await result.push('/design'); await result.isReady()
  return result
}

describe('卡片交互隔离', () => {
  it('任务左侧选择只改变选中状态，标题和卡片各只打开一次详情', async () => {
    const mission = { id: 'm', title: '可选择任务', type: 'Task', priority: 'P2', status: 'Open', creator: { display_name: '成员' }, tags: [] } as unknown as Mission
    const host = defineComponent({ components: { MissionCard }, setup: () => ({ mission, ids: ref([]) }), template: `<el-checkbox-group v-model="ids"><MissionCard :mission="mission" open-in-drawer><template #selection><el-checkbox value="m" aria-label="选择任务" /></template></MissionCard></el-checkbox-group>` })
    const wrapper = mount(host, { global: { plugins: [ElementPlus, await router()] } }); wrappers.push(wrapper)
    const card = wrapper.findComponent(MissionCard)
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.vm.ids).toEqual(['m'])
    expect(card.emitted('open')).toBeUndefined()
    const title = card.get('button.app-link')
    expect(title.attributes('type')).toBe('button')
    await title.trigger('click')
    expect(card.emitted('open')).toEqual([['m']])
    await card.trigger('click')
    expect(card.emitted('open')).toHaveLength(2)
  })

  it('通知选择不标已读，打开成功后进入关联任务', async () => {
    vi.mocked(listNotifications).mockResolvedValue({ results: [{ id: 'n', mission: 'm', mission_title: '通知任务', payload: { summary: '待验收' }, created_at: '2026-10-25', read_at: null }] as never, count: 1, next: null, previous: null })
    vi.mocked(readNotifications).mockResolvedValue({ updated: 1 } as never)
    const wrapper = mount(NotificationsView, { global: { plugins: [ElementPlus], stubs: { MissionDetailDrawer: true } } }); wrappers.push(wrapper)
    await flushPromises()
    await wrapper.get('.notification-card input[type="checkbox"]').setValue(true)
    expect(readNotifications).not.toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'MissionDetailDrawer' }).attributes('open')).toBe('false')
    await wrapper.get('button.app-link').trigger('click'); await flushPromises()
    expect(readNotifications).toHaveBeenCalledExactlyOnceWith(['n'])
    expect(wrapper.findComponent({ name: 'MissionDetailDrawer' }).props('missionId')).toBe('m')
  })

  it('设计展开按钮只展开子树，卡片标题保留路由链接', async () => {
    vi.mocked(listDesignElements).mockResolvedValueOnce({ results: [{ id: 'd', title: '设计条目', kind: 'Design', has_children: true }] as never, count: 1, next: null, previous: null }).mockResolvedValue({ results: [{ id: 'a', title: '子设计', kind: 'Design', has_children: false }] as never, count: 1, next: null, previous: null })
    const navigation = await router()
    const wrapper = mount(DesignTreeBranch, { props: { archived: 'false', kind: 'Design' }, global: { plugins: [ElementPlus, navigation] } }); wrappers.push(wrapper)
    await flushPromises()
    expect(listDesignElements).toHaveBeenCalledWith(expect.objectContaining({ parent: 'root', kind: 'Design' }))
    expect(wrapper.get('.design-item-card a.app-link').attributes('href')).toBe('/design/d')
    await wrapper.get('button[aria-expanded]').trigger('click'); await flushPromises()
    expect(navigation.currentRoute.value.path).toBe('/design')
    expect(wrapper.get('button[aria-expanded]').attributes('aria-expanded')).toBe('true')
    expect(listDesignElements).toHaveBeenLastCalledWith(expect.objectContaining({ parent: 'd', kind: 'Design' }))
    expect(wrapper.get('.design-item-card').get('.design-children .design-item-card').text()).toContain('子设计')
    expect(wrapper.get('.design-children a.app-link').attributes('href')).toBe('/design/a')
    await wrapper.get('button[aria-expanded]').trigger('click')
    expect(wrapper.find('.design-children').exists()).toBe(false)
  })

  it('设计与生产按钮导航保留当前页标识和目标路由', async () => {
    const navigation = await router()
    const wrapper = mount(DesignNavigation, { props: { active: 'design' }, global: { plugins: [ElementPlus, navigation] } }); wrappers.push(wrapper)
    expect(wrapper.get('button[aria-current="page"]').text()).toBe('设计与资产')
    await wrapper.findAll('button')[1]!.trigger('click'); await flushPromises()
    expect(navigation.currentRoute.value.name).toBe('production-templates')
  })
})
