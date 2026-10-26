import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AssistancePanel from '../components/AssistancePanel.vue'
import { listAgentDevices, createAssistance, getAssistance, cancelAssistance } from '../api/agentBridge'
import type { AssistanceRequest } from '../api/agentBridge'

vi.mock('../api/agentBridge', () => ({ listAgentDevices: vi.fn(), createAssistance: vi.fn(), getAssistance: vi.fn(), cancelAssistance: vi.fn() }))
const draft = { title: '原文', content: '说明', kind: 'Asset' }
const candidate: AssistanceRequest = { id: 'r', kind: 'design_polish', status: 'succeeded', input: { draft }, result: { title: '建议标题', content: '<script>alert(1)</script>说明', summary: '润色', questions: [] }, error: '', stale_reason: '', stopped_at: '2026-10-26', created_at: '2026-10-26' }
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.mocked(listAgentDevices).mockResolvedValue({ results: [{ id: 'd', name: '电脑', capabilities: ['design_polish', 'review_assist'], expires_at: '2099-01-01', revoked_at: null, last_seen_at: new Date().toISOString() }], count: 1, next: null, previous: null })
  vi.mocked(createAssistance).mockResolvedValue(candidate)
  vi.mocked(getAssistance).mockResolvedValue(candidate)
})
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; vi.resetAllMocks() })
async function render() {
  const wrapper = mount(AssistancePanel, { props: { kind: 'design_polish', draft }, global: { plugins: [ElementPlus], stubs: { RouterLink: true, ElementMultiSelect: true } } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
async function click(wrapper: ReturnType<typeof mount>, text: string) {
  await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click'); await flushPromises()
}
describe('本地辅助人工采纳', () => {
  it('预览不生成，返回候选不采纳，逐字段确认只发出表单事件', async () => {
    const w = await render()
    await click(w, '预览发送内容')
    expect(createAssistance).not.toHaveBeenCalled()
    await click(w, '生成候选')
    expect(w.emitted('adopt')).toBeUndefined()
    expect(w.find('script').exists()).toBe(false)
    await click(w, '采纳标题')
    expect(w.emitted('adopt')).toEqual([['title', '建议标题']])
    expect(getAssistance).toHaveBeenCalledWith('r')
  })
  it('生成期间修改草稿须明确比较才能采纳，过期建议禁止采纳', async () => {
    const w = await render(); await click(w, '预览发送内容'); await click(w, '生成候选')
    await w.setProps({ draft: { ...draft, title: '我继续编辑了' } })
    expect(w.text()).toContain('草稿已改变')
    expect(w.findAll('button').find(b => b.text() === '采纳标题')!.attributes('disabled')).toBeDefined()
    await w.find('input[type="checkbox"]').setValue(true)
    vi.mocked(getAssistance).mockResolvedValue({ ...candidate, stale_reason: '版本已变化' })
    await click(w, '采纳标题')
    expect(w.emitted('adopt')).toBeUndefined()
    expect(w.text()).toContain('版本已变化')
  })
  it('取消清除候选，不发出采纳事件', async () => {
    const w = await render(); await click(w, '预览发送内容'); await click(w, '生成候选')
    vi.mocked(cancelAssistance).mockResolvedValue({ ...candidate, status: 'cancelled', result: null })
    await click(w, '放弃候选')
    expect(w.emitted('adopt')).toBeUndefined()
    expect(w.text()).not.toContain('采纳标题')
  })
  it('未知网络结果重发同一幂等键，避免重复生成', async () => {
    const w = await render(); await click(w, '预览发送内容')
    vi.mocked(createAssistance).mockRejectedValueOnce(new Error('断线')).mockResolvedValueOnce(candidate)
    await click(w, '生成候选'); await click(w, '生成候选')
    expect(vi.mocked(createAssistance).mock.calls[0]![0].idempotency_key).toEqual(vi.mocked(createAssistance).mock.calls[1]![0].idempotency_key)
  })
})
