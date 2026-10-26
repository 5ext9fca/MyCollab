// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { CHUNK_BYTES, FileReceiver, MAX_FILE_BYTES, sha256, waitForBuffer } from '../transfers/protocol'

const buffer = (text: string) => new TextEncoder().encode(text).buffer

describe('文件直传校验协议', () => {
  it('使用 SHA-256 标准向量并支持空文件', async () => {
    expect(await sha256(buffer('abc'))).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    const empty = new FileReceiver(0, await sha256(buffer('')))
    expect((await empty.finish()).blob.size).toBe(0)
  })
  it('多块接收后验证完整文件，内容与原始字节一致', async () => {
    const data = new Uint8Array(CHUNK_BYTES * 2 + 7).map((_, i) => i % 251)
    const hash = await sha256(data.buffer)
    const receiver = new FileReceiver(data.length, hash)
    for (let start = 0; start < data.length; start += CHUNK_BYTES) receiver.append(data.slice(start, start + CHUNK_BYTES).buffer)
    const result = await receiver.finish()
    expect(result.checksum).toBe(hash)
    expect(new Uint8Array(await result.blob.arrayBuffer())).toEqual(data)
    await expect(receiver.finish()).rejects.toThrow()
  })
  it('字节损坏时拒绝提供文件', async () => {
    const receiver = new FileReceiver(3, await sha256(buffer('abc')))
    receiver.append(buffer('abd'))
    await expect(receiver.finish()).rejects.toThrow('SHA-256')
  })
  it('拒绝截断、超长、异常分块及完成后追加', async () => {
    const receiver = new FileReceiver(3, await sha256(buffer('abc')))
    receiver.append(buffer('ab'))
    await expect(receiver.finish()).rejects.toThrow('未完整')
    expect(() => receiver.append(buffer('cd'))).toThrow()
    expect(() => receiver.append('c')).toThrow()
    expect(() => receiver.append(new ArrayBuffer(CHUNK_BYTES + 1))).toThrow()
    receiver.clear()
    expect(() => receiver.append(buffer('c'))).toThrow()
    expect(() => new FileReceiver(MAX_FILE_BYTES + 1, '0'.repeat(64))).toThrow()
  })
  it('缓冲区有压力时暂停，低水位后恢复，取消会解除等待', async () => {
    class Channel extends EventTarget { bufferedAmount = 1024 * 1024; readyState = 'open' }
    const channel = new Channel()
    const abort = new AbortController()
    let ready = false
    const waiting = waitForBuffer(channel as unknown as RTCDataChannel, abort.signal).then(() => { ready = true })
    await Promise.resolve()
    expect(ready).toBe(false)
    channel.dispatchEvent(new Event('bufferedamountlow'))
    await waiting
    expect(ready).toBe(true)
    const cancelled = waitForBuffer(channel as unknown as RTCDataChannel, abort.signal)
    abort.abort()
    await expect(cancelled).rejects.toThrow()
  })
})
