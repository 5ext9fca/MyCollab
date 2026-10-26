import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AgentRequirementsExport from '../components/AgentRequirementsExport.vue'
import { listAgentDevices, createAssistance, getAssistance } from '../api/agentBridge'
import type { AssistanceRequest } from '../api/agentBridge'
import type { Mission } from '../api/types'
vi.mock('../api/agentBridge', () => ({ listAgentDevices: vi.fn(), createAssistance: vi.fn(), getAssistance: vi.fn(), cancelAssistance: vi.fn() }))
const mission = { id: 'mission', version: 3 } as Mission
const item: AssistanceRequest = { id: 'request', kind: 'agent_requirements', status: 'queued', input: {}, result: null, error: '', stale_reason: '', stopped_at: null, created_at: '' }
let wrapper: VueWrapper
beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(listAgentDevices).mockResolvedValue({ results: [{ id: 'device', name: '本机', capabilities: ['agent_requirements'], expires_at: '2099-01-01', revoked_at: null, last_seen_at: null }], count: 1, next: null, previous: null })
  vi.mocked(createAssistance).mockResolvedValue(item)
  vi.mocked(getAssistance).mockResolvedValue(item)
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.restoreAllMocks(); vi.resetAllMocks() })
async function render() {
  wrapper = mount(AgentRequirementsExport, { props: { mission }, global: { plugins: [ElementPlus], stubs: { RouterLink: true } } })
  await flushPromises()
}
async function click(text: string) { await wrapper.findAll('button').find(button => button.text() === text)!.trigger('click'); await flushPromises() }
describe('导出 Agent 需求文档', () => {
  it('点击后才创建本地整理请求，轮询返回 Markdown，卸载后停止', async () => {
    await render()
    expect(listAgentDevices).not.toHaveBeenCalled()
    await click('导出为Agent需求文档')
    expect(createAssistance).toHaveBeenCalledWith(expect.objectContaining({ kind: 'agent_requirements', object_id: 'mission', base_version: 3, draft: {} }))
    vi.mocked(getAssistance).mockResolvedValue({ ...item, status: 'succeeded', result: { markdown: '# Agent 需求文档\n\n绿色披风<script>alert(1)</script>' } })
    await vi.advanceTimersByTimeAsync(5000); await flushPromises()
    expect(wrapper.find('details').element.open).toBe(false)
    expect(wrapper.find('summary').text()).toBe('需求文档预览')
    expect(wrapper.text()).toContain('绿色披风')
    expect(wrapper.find('.markdown script').exists()).toBe(false)
    expect(wrapper.text()).toContain('下载 Markdown')
    const count = vi.mocked(getAssistance).mock.calls.length
    wrapper.unmount(); await vi.advanceTimersByTimeAsync(60000)
    expect(getAssistance).toHaveBeenCalledTimes(count)
  })
  it('未知创建结果重用相同幂等键，无可用设备不发请求', async () => {
    vi.mocked(createAssistance).mockRejectedValueOnce(new Error('断网'))
    await render(); await click('导出为Agent需求文档'); await click('导出为Agent需求文档')
    expect(vi.mocked(createAssistance).mock.calls[0]![0]).toEqual(vi.mocked(createAssistance).mock.calls[1]![0])
    wrapper.unmount(); vi.mocked(createAssistance).mockClear()
    vi.mocked(listAgentDevices).mockResolvedValue({ results: [], count: 0, next: null, previous: null })
    await render(); await click('导出为Agent需求文档')
    expect(createAssistance).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先绑定')
  })
  it('下载前复核来源，旧来源结果不生成文件', async () => {
    vi.mocked(createAssistance).mockResolvedValue({ ...item, status: 'succeeded', result: { markdown: '# Agent 需求文档' } })
    vi.mocked(getAssistance).mockResolvedValue({ ...item, status: 'succeeded', result: { markdown: '# Agent 需求文档' }, stale_reason: '资产已变化' })
    await render(); await click('导出为Agent需求文档'); await click('下载 Markdown')
    expect(wrapper.text()).toContain('资产已变化')
    expect(wrapper.findAll('button').find(button => button.text() === '下载 Markdown')!.attributes('disabled')).toBeDefined()
  })
  it('下载实际模型返回的 Markdown 文件', async () => {
    const ready = { ...item, status: 'succeeded' as const, result: { markdown: '# Agent 需求文档\n整理后的内容' } }
    vi.mocked(createAssistance).mockResolvedValue(ready); vi.mocked(getAssistance).mockResolvedValue(ready)
    const createURL = vi.fn().mockReturnValue('blob:markdown')
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createURL; static revokeObjectURL = vi.fn() })
    const clickLink = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await render(); await click('导出为Agent需求文档'); await click('下载 Markdown')
    expect(createURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(clickLink).toHaveBeenCalledOnce()
    expect((createURL.mock.calls[0]![0] as Blob).type).toBe('text/markdown;charset=utf-8')
    vi.unstubAllGlobals()
  })
})
