import { defineComponent } from 'vue'
import { expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import AppLayout from '../components/AppLayout.vue'

vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ user: null }) }))
vi.mock('../api/notifications', () => ({ notificationSummary: vi.fn() }))

it('跨页面跳转及返回时菜单跟随当前页面，详情保持所属栏目', async () => {
  const pages = [
    ['missions', 'square'], ['agent-devices', 'agent-devices'],
    ['design/templates', 'production-templates'], ['missions/123', 'mission-detail'],
  ]
  const router = createRouter({ history: createMemoryHistory(), routes: pages.map(([path, name]) => ({ path: `/${path}`, name, component: { template: '<div />' } })) })
  await router.push('/missions')
  const wrapper = mount(AppLayout, { global: { plugins: [router, ElementPlus], stubs: { ThemeSelect: true } } })
  try {
    for (const [path, label] of [
      ['/missions', '任务广场'], ['/agent-devices', '本地 Agent'],
      ['/design/templates', '设计与资产'], ['/missions/123', '任务广场'],
    ]) {
      await router.push(path!); await flushPromises()
      expect(wrapper.find('.el-menu-item.is-active').text()).toBe(label)
    }
    router.back(); await flushPromises()
    expect(wrapper.find('.el-menu-item.is-active').text()).toBe('设计与资产')
  } finally { wrapper.unmount() }
})


it('切换任务详情重新挂载，同任务锚点变化保留页面状态', async () => {
  const opened: string[] = []
  const Detail = defineComponent({ props: ['id'], setup(props) { opened.push(props.id); return {} }, template: '<div>任务详情</div>' })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/missions/:id', name: 'mission-detail', component: Detail, props: true }] })
  await router.push('/missions/first')
  const wrapper = mount(AppLayout, { global: { plugins: [router, ElementPlus], stubs: { ThemeSelect: true } } })
  try {
    await flushPromises()
    await router.push('/missions/second'); await flushPromises()
    expect(opened).toEqual(['first', 'second'])
    await router.push('/missions/second#dependencies'); await flushPromises()
    expect(opened).toEqual(['first', 'second'])
  } finally { wrapper.unmount() }
})
