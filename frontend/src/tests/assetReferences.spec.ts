import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'
import MissionForm from '../components/MissionForm.vue'
import AssetSelect from '../components/AssetSelect.vue'
import ElementMultiSelect from '../components/ElementMultiSelect.vue'
import { getDesignElement, listDesignElements } from '../api/designElements'

vi.mock('../api/auth', () => ({ listTeamMembers: vi.fn().mockResolvedValue([]) }))
vi.mock('../api/milestones', () => ({ listMilestones: vi.fn().mockResolvedValue({ results: [] }) }))
vi.mock('../api/missions', () => ({ listTags: vi.fn().mockResolvedValue([]) }))
vi.mock('../api/designElements', () => ({ listDesignElements: vi.fn(), getDesignElement: vi.fn() }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; vi.clearAllMocks() })

describe('任务独立引用设计与资产', () => {
  it('编辑表单同时提交设计依据和多项资产，清空资产不影响设计', async () => {
    const wrapper = mount(MissionForm, {
      props: { initial: { title: '接入星星', design_element_id: 'design', asset_ids: ['icon', 'audio'] } },
      global: { plugins: [ElementPlus], stubs: {
        MarkdownEditor: true, DesignElementSelect: true,
        AssetSelect: defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], template: '<button type="button" class="clear-assets" @click="$emit(\'update:modelValue\', [])">清空资产</button>' }),
      } },
    })
    wrappers.push(wrapper)
    await flushPromises()
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ design_element_id: 'design', asset_ids: ['icon', 'audio'] })
    await wrapper.find('.clear-assets').trigger('click')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({ design_element_id: 'design', asset_ids: [] })
  })
  it('前置依赖按当前类型查询，排除自身并随类型切换刷新', async () => {
    vi.mocked(listDesignElements).mockResolvedValue({ count: 2, next: null, previous: null, results: [
      { id: 'self', title: '当前设计', kind: 'Design', archived: false },
      { id: 'other', title: '前置设计', kind: 'Design', archived: false },
    ] } as never)
    const wrapper = mount(ElementMultiSelect, { props: { kind: 'Design', excludeId: 'self', label: '前置依赖' }, global: { plugins: [ElementPlus] } })
    wrappers.push(wrapper); await flushPromises()
    expect(listDesignElements).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'Design' }))
    expect(wrapper.findAllComponents({ name: 'ElOption' }).map(option => option.props('value'))).toEqual(['other'])
    vi.mocked(listDesignElements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    await wrapper.setProps({ kind: 'Asset' }); await flushPromises()
    expect(listDesignElements).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'Asset' }))
    expect(wrapper.findAllComponents({ name: 'ElOption' })).toHaveLength(0)
  })
  it('资产选择器仅查询资产并回显已归档的既有引用', async () => {
    vi.mocked(listDesignElements).mockResolvedValue({ count: 1, next: null, previous: null, results: [{ id: 'active', title: '音效', kind: 'Asset', archived: false }] } as never)
    vi.mocked(getDesignElement).mockResolvedValue({ id: 'archived', title: '旧图标', kind: 'Asset', archived: true } as never)
    const wrapper = mount(AssetSelect, { props: { modelValue: ['archived'] }, global: { plugins: [ElementPlus] } })
    wrappers.push(wrapper); await flushPromises()
    expect(listDesignElements).toHaveBeenCalledWith(expect.objectContaining({ kind: 'Asset', archived: 'false' }))
    expect(getDesignElement).toHaveBeenCalledWith('archived')
    expect(wrapper.text()).toContain('旧图标（已归档）')
  })
})
