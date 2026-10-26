import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AgentInteractionView from '../views/AgentInteractionView.vue'
import { getMission } from '../api/missions'
import type { Mission } from '../api/types'
vi.mock('../api/missions', () => ({ getMission: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { kind: 'image' } }) }))
let wrapper: VueWrapper
const mission = { id: 'one', title: '资产制作' } as Mission
beforeEach(() => { vi.mocked(getMission).mockResolvedValue(mission) })
afterEach(() => { wrapper?.unmount(); vi.resetAllMocks() })
async function render() {
  wrapper = mount(AgentInteractionView, { props: { id: 'one' }, global: { plugins: [ElementPlus], stubs: { RouterLink: true, AgentPanel: true } } })
  await flushPromises()
}
describe('独立 Agent 交互页', () => {
  it('读取当前 Mission 并支持图像入口，返回链接位于卡片中', async () => {
    await render()
    expect(getMission).toHaveBeenCalledWith('one')
    expect(wrapper.findComponent({ name: 'AgentPanel' }).props('mission')).toEqual(mission)
    expect(wrapper.findComponent({ name: 'AgentPanel' }).props('initialKind')).toBe('image')
    expect(wrapper.find('.el-card router-link-stub').attributes('to')).toBe('/missions/one')
  })
  it('加载失败不显示交互操作，允许重新读取', async () => {
    vi.mocked(getMission).mockRejectedValueOnce(new Error('无访问权限'))
    await render()
    expect(wrapper.text()).toContain('无访问权限')
    expect(wrapper.findComponent({ name: 'AgentPanel' }).exists()).toBe(false)
    await wrapper.find('button').trigger('click'); await flushPromises()
    expect(wrapper.findComponent({ name: 'AgentPanel' }).exists()).toBe(true)
  })
  it('切换 Mission 忽略迟到响应', async () => {
    let resolve!: (value: Mission) => void
    vi.mocked(getMission).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    await render()
    vi.mocked(getMission).mockResolvedValue({ ...mission, id: 'two', title: '新任务' })
    await wrapper.setProps({ id: 'two' }); await flushPromises()
    resolve(mission); await flushPromises()
    expect(wrapper.text()).toContain('新任务')
    expect(wrapper.text()).not.toContain('资产制作')
  })
})
