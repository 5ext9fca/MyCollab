import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SavedViewsBar from '../components/SavedViewsBar.vue'
import * as api from '../api/savedViews'
import { useAuthStore } from '../stores/auth'
const { route, push } = vi.hoisted(() => ({ route: { query: {} as Record<string, string> }, push: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push, replace: vi.fn() }) }))
vi.mock('../api/savedViews', async importOriginal => ({ ...await importOriginal<typeof api>(), getSavedView: vi.fn(), listSavedViews: vi.fn(), createSavedView: vi.fn(), updateSavedView: vi.fn(), resolveSavedView: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), success: vi.fn() } }))
const definition = { filters: { assignee: 'me' }, ordering: null, date_window: null, zoom: null }
const row = { id: 'v', name: '我的视图', owner: 1, owner_name: 'a', visibility: 'Private', target: 'List', definition, version: 3, warnings: [] } as api.SavedView
const global = { stubs: { MissionQueryForm: true, ElButton: { template: '<button><slot /></button>' }, ElDialog: { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' }, ElForm: { template: '<div><slot /></div>' }, ElFormItem: { template: '<div><slot /></div>' }, ElSelect: true, ElInput: true, ElTag: { template: '<span><slot /></span>' } } }
beforeEach(() => { vi.clearAllMocks(); setActivePinia(createPinia()); useAuthStore().user = { id: 1, is_staff: false } as never; route.query = {}; vi.mocked(api.getSavedView).mockResolvedValue(row); vi.mocked(api.listSavedViews).mockResolvedValue({ results: [row], count: 1, next: null, previous: null }) })
describe('保存视图', () => {
  it('定义仅保存白名单查询，角色整数和动态 me 不混淆，路由不能由定义指定', () => {
    expect(api.definitionFromQuery({ assignee: 'me', reviewer: '2', tag: ['甲', '甲'], page: 2, selected: 'x', blocked: 'false' }, 'List')).toEqual({ filters: { assignee: 'me', reviewer: 2, tag: ['甲'], blocked: false }, ordering: null, date_window: null, zoom: null })
    expect(api.viewLocation('Gantt', { assignee: 2, date_from: '2026-10-25' }, 'v').path).toBe('/workspace')
  })
  it('手动修改不自动写回，更新与另存为都是明确动作', async () => {
    route.query = { saved_view: 'v' }
    vi.mocked(api.updateSavedView).mockResolvedValue({ ...row, version: 4 })
    vi.mocked(api.createSavedView).mockResolvedValue({ ...row, id: 'copy' })
    const wrapper = mount(SavedViewsBar, { props: { query: { assignee: '1' }, target: 'List' }, global }); await flushPromises()
    await wrapper.setProps({ query: { assignee: '1', priority: 'P0' } }); await flushPromises()
    expect(api.updateSavedView).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('已修改')
    const click = async (label: string) => { await wrapper.findAll('button').find(b => b.text() === label)!.trigger('click'); await flushPromises() }
    await click('更新视图'); await click('确认保存')
    expect(api.updateSavedView).toHaveBeenCalledWith('v', expect.objectContaining({ definition: expect.objectContaining({ filters: { assignee: 'me', priority: 'P0' } }) }), 3)
    await click('另存为'); await click('确认保存'); expect(api.createSavedView).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('打开视图每次服务端解析，恢复固定路由和查询', async () => {
    vi.mocked(api.resolveSavedView).mockResolvedValue({ target: 'List', query: { assignee: 1, tag: ['甲', '乙'] }, today: '2026-10-25', warnings: [] })
    const wrapper = mount(SavedViewsBar, { props: { query: {}, target: 'List' }, global })
    await wrapper.findAll('button').find(b => b.text() === '打开 / 管理视图')!.trigger('click'); await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '打开')!.trigger('click'); await flushPromises()
    expect(api.resolveSavedView).toHaveBeenCalledWith('v')
    expect(push).toHaveBeenCalledWith({ path: '/missions', query: { assignee: '1', tag: ['甲', '乙'], status: 'all', saved_view: 'v' } })
    wrapper.unmount()
  })
})
