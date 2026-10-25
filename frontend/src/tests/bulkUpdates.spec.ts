import { flushPromises, mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import BulkMissionEditor from '../components/BulkMissionEditor.vue'
import * as missions from '../api/missions'
import type { Mission } from '../api/types'
vi.mock('../api/missions', () => ({ bulkUpdateMissions: vi.fn(), getMission: vi.fn() }))
vi.mock('../api/notifications', () => ({ notifyChanged: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
const Button = { props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot /></button>' }
const global = { stubs: { ElButton: Button, ElDialog: { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' }, ElForm: { template: '<div><slot /></div>' }, ElFormItem: { template: '<div><slot /></div>' }, ElSelect: { props: ['modelValue'], emits: ['update:modelValue'], template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>' }, ElOption: { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' }, ElAlert: true, RouterLink: { template: '<a><slot /></a>' } } }
const rows = [{ id: 'a', title: '甲', version: 1, priority: 'P2' }, { id: 'b', title: '乙', version: 2, priority: 'P2' }] as Mission[]
function setup() { return mount(BulkMissionEditor, { props: { missions: rows, selectedIds: ['a', 'b'], resetKey: 'page1' }, global }) }
async function click(wrapper: ReturnType<typeof setup>, label: string) { await wrapper.findAll('button').find(b => b.text() === label)!.trigger('click'); await flushPromises() }
async function preview(wrapper: ReturnType<typeof setup>) { await click(wrapper, '批量编辑计划'); await wrapper.find('select').setValue('set'); await click(wrapper, '预览变更') }
beforeEach(() => vi.clearAllMocks())
describe('批量编辑交互', () => {
  it('预览不写入，部分失败必须刷新并重新确认且仅重试失败项', async () => {
    vi.mocked(missions.bulkUpdateMissions).mockResolvedValueOnce({ results: [{ id: 'a', success: true, status: 200 }, { id: 'b', success: false, status: 409, error: { code: 'version_conflict', message: '版本冲突', field_errors: {} } }], succeeded_count: 1, failed_count: 1 }).mockResolvedValue({ results: [{ id: 'b', success: true, status: 200 }], succeeded_count: 1, failed_count: 0 })
    vi.mocked(missions.getMission).mockResolvedValue({ ...rows[1]!, version: 8 })
    const wrapper = setup(); await preview(wrapper)
    expect(missions.bulkUpdateMissions).not.toHaveBeenCalled()
    await click(wrapper, '确认逐项执行')
    expect(wrapper.emitted('update:selectedIds')?.at(-1)).toEqual([['b']])
    expect(wrapper.text()).toContain('版本冲突')
    await click(wrapper, '读取最新任务')
    expect(missions.bulkUpdateMissions).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('版本 8')
    await click(wrapper, '预览变更'); await click(wrapper, '确认逐项执行')
    expect(missions.bulkUpdateMissions).toHaveBeenLastCalledWith([{ id: 'b', expected_version: 8 }], { priority: 'P2' })
    wrapper.unmount()
  })
  it('网络中断不重发，翻页清空选择', async () => {
    vi.mocked(missions.bulkUpdateMissions).mockRejectedValue(new Error('网络中断'))
    const wrapper = setup(); await preview(wrapper); await click(wrapper, '确认逐项执行')
    expect(missions.bulkUpdateMissions).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('button').some(b => b.text() === '读取最新任务')).toBe(true)
    await wrapper.setProps({ resetKey: 'page2' })
    expect(wrapper.emitted('update:selectedIds')?.at(-1)).toEqual([[]]); wrapper.unmount()
  })
  it('请求进行中禁用重复确认', async () => {
    let finish!: (value: never) => void
    vi.mocked(missions.bulkUpdateMissions).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = setup(); await preview(wrapper)
    const button = wrapper.findAll('button').find(b => b.text() === '确认逐项执行')!
    await button.trigger('click'); await button.trigger('click')
    expect(missions.bulkUpdateMissions).toHaveBeenCalledTimes(1)
    finish({ results: [], succeeded_count: 0, failed_count: 0 } as never); await flushPromises(); wrapper.unmount()
  })
})
