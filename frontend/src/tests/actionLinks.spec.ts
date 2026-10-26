import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import MissionCard from '../components/MissionCard.vue'
import MissionDesignLink from '../components/MissionDesignLink.vue'
import MissionSubscription from '../components/MissionSubscription.vue'
import MarkdownContent from '../components/MarkdownContent.vue'
import { getSubscription, putSubscription } from '../api/notifications'
import type { Mission } from '../api/types'
vi.mock('../api/notifications', () => ({ getSubscription: vi.fn(), putSubscription: vi.fn() }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.clearAllMocks() })
async function navigation() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/missions/:id', name: 'mission-detail', component: { template: '<div />' } },
    { path: '/design/:id', name: 'design', component: { template: '<div />' } },
  ] })
  await router.push('/missions/start')
  return router
}
it('受阻链接进入依赖区域且不触发父卡片打开抽屉', async () => {
  const router = await navigation()
  const mission = { id: 'blocked', title: '受阻任务', type: 'Task', priority: 'P2', status: 'Open', is_blocked: true, creator: { display_name: '成员' }, tags: [] } as unknown as Mission
  const wrapper = mount(MissionCard, { props: { mission, openInDrawer: true }, global: { plugins: [router, ElementPlus] } }); wrappers.push(wrapper)
  const link = wrapper.get('a[aria-label="受阻：查看前置依赖"]')
  expect(link.attributes('href')).toBe('/missions/blocked#dependencies')
  await link.trigger('click'); await flushPromises()
  expect(router.currentRoute.value.fullPath).toBe('/missions/blocked#dependencies')
  expect(wrapper.emitted('open')).toBeUndefined()
})
it('资产入口保持独立卡片和归档提示', async () => {
  const wrapper = mount(MissionDesignLink, { props: { assets: [{ id: 'asset', title: '角色资产', archived: true }] as never }, global: { plugins: [await navigation()] } }); wrappers.push(wrapper)
  expect(wrapper.get('a.app-link--action').text()).toBe('角色资产（已归档）')
  expect(wrapper.get('a').attributes('href')).toBe('/design/asset')
})
it('已关注归入功能卡片，静音操作保持版本校验并更新状态', async () => {
  vi.mocked(getSubscription).mockResolvedValue({ effective_following: true, subscription: { version: 3 } } as never)
  vi.mocked(putSubscription).mockResolvedValue({ effective_following: false, subscription: { version: 4 } } as never)
  const wrapper = mount(MissionSubscription, { props: { missionId: 'mission' }, global: { plugins: [ElementPlus] } }); wrappers.push(wrapper)
  await flushPromises()
  expect(wrapper.get('.subscription-card').text()).toContain('已关注')
  const mute = wrapper.findAll('button.app-link--action').find(b => b.text() === '静音普通动态')!
  await mute.trigger('click'); await flushPromises()
  expect(putSubscription).toHaveBeenCalledWith('mission', 'Mute', 3)
  expect(wrapper.text()).toContain('未关注普通动态')
})
it('Markdown 引用使用公共样式并保留安全清洗', () => {
  const wrapper = mount(MarkdownContent, { props: { source: '[引用](https://example.com) <a href="javascript:alert(1)" onclick="alert(1)">危险</a><script>alert(1)</script>' } }); wrappers.push(wrapper)
  expect(wrapper.findAll('a').every(a => a.classes().includes('app-link'))).toBe(true)
  expect(wrapper.get('a').classes()).not.toContain('app-link--action')
  expect(wrapper.find('script').exists()).toBe(false)
  expect(wrapper.find('[onclick]').exists()).toBe(false)
  expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
})
