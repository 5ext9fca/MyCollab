import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AgentConversation from '../components/AgentConversation.vue'
import { getInteraction, sendInteraction } from '../api/interactions'
import type { InteractionState } from '../api/interactions'
vi.mock('../api/interactions', () => ({ getInteraction: vi.fn(), sendInteraction: vi.fn() }))
let wrapper: VueWrapper
const state: InteractionState = { available: true, active: true, attempt_id: 'attempt', session_nonce: 'nonce', supports_followup: true, supports_permissions: true,
  events: [{ seq: 1, kind: 'assistant_message', payload: { text: '<script>危险文本</script>请确认文件' }, created_at: '2026-10-26' }], next_cursor: 1, has_more: false, commands: [],
  permissions: [{permission_id: 'permission', operation: {action: 'edit', paths: ['rules.py']}, operation_digest: 'digest', status: 'pending', decision: '', expires_at: '2099-01-01'}] }
beforeEach(() => { vi.useFakeTimers(); vi.mocked(getInteraction).mockResolvedValue(state); vi.mocked(sendInteraction).mockResolvedValue({command_id: 'command', status: 'queued'}) })
afterEach(() => {wrapper?.unmount(); vi.useRealTimers(); vi.resetAllMocks()})
async function render() { wrapper = mount(AgentConversation, {props: {requestId: 'request', status: 'running'}, global: {plugins: [ElementPlus]}}); await flushPromises() }
async function click(label: string) { await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click'); await flushPromises() }
describe('执行中私有对话', () => {
  it('消息发送失败重试同一编号，不自动执行第二次；文本不作为 HTML', async () => {
    await render()
    expect(wrapper.find('script').exists()).toBe(false)
    await wrapper.find('textarea').setValue('增加边界测试')
    vi.mocked(sendInteraction).mockRejectedValueOnce(new Error('断线'))
    await click('发送消息')
    expect(wrapper.text()).toContain('发送结果尚未确认')
    await click('重试同一指令')
    expect(vi.mocked(sendInteraction).mock.calls[0]).toEqual(vi.mocked(sendInteraction).mock.calls[1])
    expect(vi.mocked(sendInteraction).mock.calls[0]![1]).toMatchObject({attempt_id:'attempt',session_nonce:'nonce',kind:'followup',payload:{text:'增加边界测试'}})
  })
  it('批准仅绑定当前操作与会话，没有永久授权', async () => {
    await render(); await click('仅批准这一次')
    expect(sendInteraction).toHaveBeenCalledWith('request',expect.objectContaining({attempt_id:'attempt',session_nonce:'nonce',kind:'permission_reply',payload:{permission_id:'permission',operation_digest:'digest',decision:'approve'}}))
    expect(wrapper.text()).not.toContain('始终允许')
  })
  it('无能力或会话终态不提供发送和批准入口', async () => {
    vi.mocked(getInteraction).mockResolvedValue({...state,active:false})
    await render()
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.findAll('button').some(b=>b.text()==='仅批准这一次')).toBe(false)
    await vi.advanceTimersByTimeAsync(20000)
    expect(getInteraction).toHaveBeenCalledTimes(1)
  })
  it('按游标读取且卸载停止轮询', async () => {
    await render()
    vi.mocked(getInteraction).mockResolvedValue({...state,events:[]})
    await vi.advanceTimersByTimeAsync(5000)
    expect(getInteraction).toHaveBeenLastCalledWith('request',1)
    expect(wrapper.text().split('请确认文件')).toHaveLength(2)
    wrapper.unmount(); await vi.advanceTimersByTimeAsync(20000)
    expect(getInteraction).toHaveBeenCalledTimes(2)
  })
})
