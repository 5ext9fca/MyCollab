import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElSelect } from 'element-plus'
import ElementPlus from 'element-plus'
import ProductionPanel from '../components/ProductionPanel.vue'
import ProductionStepsEditor from '../components/ProductionStepsEditor.vue'
import { getProduction, instantiateProduction, listProductionTemplates } from '../api/productionTemplates'
import { listMilestones } from '../api/milestones'
import type { DesignElement, ProductionTemplate } from '../api/types'
vi.mock('../api/productionTemplates', () => ({ getProduction: vi.fn(), instantiateProduction: vi.fn(), listProductionTemplates: vi.fn() }))
vi.mock('../api/milestones', () => ({ listMilestones: vi.fn() }))
const asset = { id: 'asset', title: '森林守卫', version: 4, kind: 'Asset', archived: false, allowed_actions: ['edit'], progress: {} } as DesignElement
const template: ProductionTemplate = { id: 'template', name: '角色', version: 2, description: '', created_by: { id: 1, username: 'a', display_name: '作者' }, archived: false, created_at: '2026-10-25', updated_at: '2026-10-25', allowed_actions: ['edit'], steps: [
  { key: 'model', title: '建模', content: '', acceptance_criteria: '', type: 'Task', priority: 'P2', tags: [], prerequisite_keys: [] },
  { key: 'audio', title: '音效', content: '', acceptance_criteria: '', type: 'Task', priority: 'P2', tags: [], prerequisite_keys: [] },
] }
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; document.body.innerHTML = ''; vi.resetAllMocks() })
async function render() {
  vi.mocked(getProduction).mockResolvedValue({ batch: null, items: [] })
  vi.mocked(listProductionTemplates).mockResolvedValue({ results: [template], next: null, previous: null, count: 1 })
  vi.mocked(listMilestones).mockResolvedValue({ results: [], next: null, previous: null, count: 0 })
  const wrapper = mount(ProductionPanel, { props: { asset }, attachTo: document.body, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
describe('资产生产模板', () => {
  it('进入页面、选择模板与预览均不写入，确认携带两个版本', async () => {
    const wrapper = await render()
    wrapper.findAllComponents(ElSelect)[0]!.vm.$emit('update:modelValue', 'template')
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '预览生产步骤')!.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('生成 2 个待认领 Mission')
    expect(instantiateProduction).not.toHaveBeenCalled()
    let finish!: (value: Awaited<ReturnType<typeof instantiateProduction>>) => void
    vi.mocked(instantiateProduction).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === '生成 2 个待认领 Mission')!
    confirm.click(); confirm.click(); await flushPromises()
    expect(instantiateProduction).toHaveBeenCalledTimes(1)
    expect(instantiateProduction).toHaveBeenCalledWith('asset', { template_id: 'template', template_version: 2, expected_version: 4, milestone_id: null })
    finish({ batch_id: 'batch', asset_version: 5, template_version: 2, items: [] }); await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('模板步骤编辑不展示私人素材插入，展示顺序不创建隐式依赖', async () => {
    const wrapper = mount(ProductionStepsEditor, { props: { modelValue: structuredClone(template.steps) }, global: { plugins: [ElementPlus] } })
    wrappers.push(wrapper)
    expect(wrapper.text()).not.toContain('插入素材')
    expect(wrapper.text()).toContain('模板只能引用 http(s) 外链')
    await wrapper.findAll('button').find(b => b.text() === '下移')!.trigger('click')
    const steps = wrapper.emitted('update:modelValue')![0]![0] as typeof template.steps
    expect(steps.map(s => s.key)).toEqual(['audio', 'model'])
    expect(steps.every(s => s.prerequisite_keys.length === 0)).toBe(true)
  })
})
