import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import DesignView from '../views/DesignView.vue'
import { ApiException } from '../api/client'
import { getDesignElement, listDesignEvents, updateDesignElement } from '../api/designElements'
import { listMissions } from '../api/missions'
import type { DesignElement } from '../api/types'

vi.mock('../api/designElements', () => ({ getDesignElement: vi.fn(), listDesignEvents: vi.fn(), updateDesignElement: vi.fn(), createDesignElement: vi.fn() }))
vi.mock('../api/missions', () => ({ listMissions: vi.fn() }))
const empty = { results: [], count: 0, next: null, previous: null }
const detail: DesignElement = {
  id: 'asset', title: '森林守卫', content: '设计内容', kind: 'Asset', archived: false,
  parent: null, ancestors: [], assets: [], referencing_designs: [], prerequisites: [], dependents: [], created_by: { id: 1, username: 'a', display_name: '作者' },
  version: 1, created_at: '2026-10-25', updated_at: '2026-10-25', allowed_actions: ['edit', 'archive'], has_children: false,
  progress: { effective_total: 0, done: 0, progress: null, blocked: 0, revalidation: 0 },
}
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; document.body.innerHTML = ''; vi.resetAllMocks() })
async function render(value = detail) {
  vi.mocked(getDesignElement).mockResolvedValue(value)
  vi.mocked(listMissions).mockResolvedValue(empty)
  vi.mocked(listDesignEvents).mockResolvedValue(empty)
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/design/:id?', name: 'design', component: DesignView },
    { path: '/missions/new', name: 'mission-create', component: { template: '<div />' } },
    { path: '/design/templates', name: 'production-templates', component: { template: '<div />' } },
    { path: '/workspace', name: 'workspace', component: { template: '<div />' } },
  ] })
  await router.push('/design/asset'); await router.isReady()
  const wrapper = mount(DesignView, { attachTo: document.body, global: { plugins: [router, ElementPlus], stubs: {
    ProductionPanel: true, DesignTreeBranch: true, DesignElementSelect: true, AssetSelect: true, ElementMultiSelect: true, MarkdownEditor: defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }), MissionDetailDrawer: true,
  } } })
  wrappers.push(wrapper); await flushPromises()
  return wrapper
}
describe('设计关联页面', () => {
  it('空进度不展示完成，资产发布链接携带相关资产，只加载直属任务', async () => {
    const wrapper = await render()
    expect(wrapper.text()).toContain('暂无有效任务')
    expect(wrapper.text()).not.toContain('100%')
    expect(listMissions).toHaveBeenCalledWith({ design_element: 'asset', production_batch: 'none', page: 1 })
    expect(wrapper.find('a[href="/missions/new?asset=asset"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/workspace?view=graph&design_element=asset"]').exists()).toBe(true)
  })
  it('设计页展示多项资产，资产页展示反向设计引用', async () => {
    const design = { id: 'design', title: '收集规则', kind: 'Design' as const, archived: false }
    const assetPage = await render({ ...detail, referencing_designs: [design] })
    expect(assetPage.text()).toContain('引用此资产的设计')
    expect(assetPage.find('a[href="/design/design"]').text()).toBe('收集规则')
    const designPage = await render({ ...detail, ...design, assets: [detail] })
    expect(designPage.text()).toContain('引用资产')
    expect(designPage.find('a[href="/missions/new?design_element=design"]').exists()).toBe(true)
    expect(designPage.find('a[href="/design/asset"]').text()).toBe('森林守卫')
  })
  it('分开显示设计树和资产树，并展示同类依赖', async () => {
    const prerequisite = { id: 'mesh', title: '角色模型', kind: 'Asset' as const, archived: false }
    const wrapper = await render({ ...detail, prerequisites: [prerequisite] })
    expect(wrapper.find('section[aria-label="设计树"]').exists()).toBe(true)
    expect(wrapper.find('section[aria-label="资产树"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('资产依赖')
    expect(wrapper.find('a[href="/design/mesh"]').text()).toBe('角色模型')
    await wrapper.findAll('button').find(b => b.text() === '编辑')!.trigger('click')
    await flushPromises()
    const selector = wrapper.findComponent({ name: 'ElementMultiSelect' })
    expect(selector.attributes('kind')).toBe('Asset')
    selector.vm.$emit('update:modelValue', ['mesh', 'rig'])
    await flushPromises()
    ;[...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === '保存')!.click()
    await flushPromises()
    expect(updateDesignElement).toHaveBeenLastCalledWith('asset', expect.objectContaining({ prerequisite_ids: ['mesh', 'rig'], expected_version: 1 }))
  })
  it('归档只读条目不显示编辑或发布按钮', async () => {
    const wrapper = await render({ ...detail, archived: true, allowed_actions: [] })
    expect(wrapper.text()).not.toContain('发布 Mission')
    expect(wrapper.findAll('button').some(b => b.text() === '编辑')).toBe(false)
  })
  it('版本冲突保留输入并刷新版本，重试携带新版本', async () => {
    const wrapper = await render()
    await wrapper.findAll('button').find(b => b.text() === '编辑')!.trigger('click')
    await flushPromises()
    const input = document.body.querySelector('.el-dialog input') as HTMLInputElement
    input.value = '保留的新标题'; input.dispatchEvent(new Event('input', { bubbles: true }))
    vi.mocked(updateDesignElement).mockRejectedValueOnce(new ApiException(409, 'version_conflict', '版本冲突', {})).mockResolvedValueOnce({ ...detail, version: 3 })
    vi.mocked(getDesignElement).mockResolvedValue({ ...detail, version: 2 })
    const save = () => [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === '保存')!.click()
    save(); await flushPromises()
    expect(input.value).toBe('保留的新标题')
    save(); await flushPromises()
    expect(updateDesignElement).toHaveBeenLastCalledWith('asset', expect.objectContaining({ title: '保留的新标题', expected_version: 2 }))
  })
})
