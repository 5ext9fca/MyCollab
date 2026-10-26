import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { useCardList } from '../composables/useCardList'
import ActionCardList from '../components/ActionCardList.vue'
import CardListSelection from '../components/CardListSelection.vue'
import ElementPlus from 'element-plus'
import type { Paginated } from '../api/types'
const result = (id: string): Paginated<{ id: string }> => ({ count: 80, results: [{ id }], next: null, previous: null })
describe('通用卡片列表', () => {
  it('统一重置页码且一次变更仅加载一次，过期请求不覆盖新列表', async () => {
    let resolveOld!: (data: Paginated<{ id: string }>) => void
    const fetchPage = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockResolvedValue(result('new'))
    const host = defineComponent({ setup() { const filters = ref({ q: '', ordering: '-created_at' }); return { filters, ...useCardList(() => filters.value, fetchPage) } }, template: '<div />' })
    const wrapper = mount(host)
    wrapper.vm.page = 3; await flushPromises()
    wrapper.vm.filters = { q: '新筛选', ordering: 'title' }; await flushPromises()
    expect(wrapper.vm.page).toBe(1)
    expect(fetchPage).toHaveBeenCalledTimes(3)
    expect(fetchPage).toHaveBeenLastCalledWith({ q: '新筛选', ordering: 'title', page: 1, page_size: 20 })
    resolveOld(result('old')); await flushPromises()
    expect(wrapper.vm.items).toEqual([{ id: 'new' }])
    wrapper.vm.page = 2; await flushPromises()
    wrapper.vm.pageSize = 50; await flushPromises()
    expect(fetchPage).toHaveBeenCalledTimes(5)
    expect(fetchPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 50 }))
    wrapper.unmount()
  })
  it('操作插槽只接收本页选择；单卡选择隔离点击，执行期间禁止选择', async () => {
    const opened = vi.fn(), action = vi.fn()
    const host = defineComponent({ components: { ActionCardList, CardListSelection }, setup() { return { selected: ref<string[]>([]), busy: ref(false), opened, action } }, template: `<ActionCardList :items="[{ id: 'a' }, { id: 'b' }]" :total="2" :loading="false" :page="1" :page-size="20" reset-key="1" v-model:selected-ids="selected" :busy="busy"><template #actions="{ selectedIds, disabled }"><button :disabled="disabled" @click="action(selectedIds)">执行</button></template><template #item="{ item }"><div class="item" @click="opened(item.id)"><CardListSelection :id="item.id" :label="item.id" /></div></template></ActionCardList>` })
    const wrapper = mount(host, { global: { plugins: [ElementPlus] } })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.get('.item input').setValue(true)
    expect(opened).not.toHaveBeenCalled()
    await wrapper.get('button').trigger('click')
    expect(action).toHaveBeenCalledWith(['a'])
    wrapper.vm.busy = true; await flushPromises()
    expect(wrapper.get('.item input').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
