// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TransferController, type TransferState } from '../transfers/controller'
import type { TransferSession } from '../api/transfers'
import { createTransfer, joinTransfer, operateTransfer } from '../api/transfers'

vi.mock('../api/transfers', () => ({ createTransfer: vi.fn(), joinTransfer: vi.fn(), operateTransfer: vi.fn() }))
const session: TransferSession = {
  id: 'test', role: 'sender', name: 'a.txt', size: 3, sha256: 'a'.repeat(64), received_sha256: '',
  status: 'waiting', error: '', sender_name: '甲', receiver_name: null, offer: '', answer: '',
  pair_expires_at: '', expires_at: '', code: 'ABCDEF123456',
}
const flush = async () => { await new Promise<void>((resolve) => setTimeout(resolve, 0)) }

describe('直传页面生命周期', () => {
  afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })
  it('取消发生在创建请求返回前，返回后仍取消服务端会话且不会启动轮询', async () => {
    let resolve!: (value: TransferSession) => void
    vi.mocked(createTransfer).mockReturnValue(new Promise((done) => { resolve = done }))
    vi.mocked(operateTransfer).mockResolvedValue({ ...session, status: 'cancelled' })
    let state!: TransferState
    const controller = new TransferController((value) => { state = value })
    const sending = controller.send(new File(['abc'], 'a.txt'))
    while (!vi.mocked(createTransfer).mock.calls.length) await flush()
    controller.cancel()
    resolve(session)
    await sending
    expect(state.active).toBe(false)
    expect(state.session).toBeNull()
    expect(state.success).toBe(false)
    expect(operateTransfer).toHaveBeenCalledWith('test', expect.any(String), 'cancel')
    controller.dispose()
  })
  it('配对不会自动接受，主动确认才发 accept', async () => {
    vi.mocked(joinTransfer).mockResolvedValue({ ...session, role: 'receiver', status: 'paired' })
    vi.mocked(operateTransfer).mockResolvedValue({ ...session, role: 'receiver', status: 'accepted' })
    const controller = new TransferController(() => {})
    await controller.join('abcdef123456')
    expect(operateTransfer).not.toHaveBeenCalled()
    await controller.accept()
    expect(operateTransfer).toHaveBeenCalledWith('test', expect.any(String), 'accept')
    controller.dispose()
  })
  it('无法验证的 completed 不显示成功，也不提供下载', async () => {
    vi.useFakeTimers()
    vi.mocked(joinTransfer).mockResolvedValue({ ...session, role: 'receiver', status: 'paired' })
    vi.mocked(operateTransfer).mockResolvedValue({ ...session, role: 'receiver', status: 'completed', received_sha256: session.sha256 })
    let state!: TransferState
    const controller = new TransferController((value) => { state = value })
    await controller.join(session.code!)
    await vi.advanceTimersByTimeAsync(1000)
    expect(state.success).toBe(false)
    expect(state.downloadUrl).toBe('')
    expect(state.active).toBe(false)
    controller.dispose()
  })
  it('轮询连续失败后停止并释放会话', async () => {
    vi.useFakeTimers()
    vi.mocked(joinTransfer).mockResolvedValue({ ...session, role: 'receiver', status: 'paired' })
    vi.mocked(operateTransfer).mockRejectedValue(new Error('网络中断'))
    let state!: TransferState
    const controller = new TransferController((value) => { state = value })
    await controller.join(session.code!)
    await vi.advanceTimersByTimeAsync(15000)
    expect(state.active).toBe(false)
    expect(state.message).toBe('网络中断')
    const count = vi.mocked(operateTransfer).mock.calls.length
    await vi.advanceTimersByTimeAsync(60000)
    expect(vi.mocked(operateTransfer).mock.calls.length).toBe(count)
    controller.dispose()
  })
})
