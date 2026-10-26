export const MAX_FILE_BYTES = 100 * 1024 * 1024
export const CHUNK_BYTES = 16 * 1024
export const BUFFER_HIGH = 512 * 1024

export async function sha256(data: ArrayBuffer): Promise<string> {
  const result = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(result), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function newToken(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(32)), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/** 仅接受有序、有限长度的二进制分块，完成后独立校验完整文件。 */
export class FileReceiver {
  private chunks: ArrayBuffer[] = []
  bytes = 0
  ended = false

  readonly size: number
  readonly expectedHash: string

  constructor(size: number, expectedHash: string) {
    this.size = size
    this.expectedHash = expectedHash
    if (!Number.isSafeInteger(size) || size < 0 || size > MAX_FILE_BYTES || !/^[a-f0-9]{64}$/.test(expectedHash)) throw new Error('文件元信息无效。')
  }

  append(data: unknown) {
    if (this.ended || !(data instanceof ArrayBuffer) || !data.byteLength || data.byteLength > CHUNK_BYTES || this.bytes + data.byteLength > this.size) throw new Error('文件分块无效或超出声明大小。')
    this.chunks.push(data)
    this.bytes += data.byteLength
  }

  async finish(): Promise<{ blob: Blob; checksum: string }> {
    if (this.ended || this.bytes !== this.size) throw new Error('文件未完整接收。')
    this.ended = true
    const blob = new Blob(this.chunks, { type: 'application/octet-stream' })
    this.chunks = []
    const checksum = await sha256(await blob.arrayBuffer())
    if (checksum !== this.expectedHash) throw new Error('SHA-256 校验不一致，已丢弃文件。')
    return { blob, checksum }
  }

  clear() { this.ended = true; this.chunks = [] }
}

export function waitForBuffer(channel: RTCDataChannel, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new Error('传输已停止。'))
  if (channel.readyState !== 'open') return Promise.reject(new Error('连接已关闭。'))
  if (channel.bufferedAmount <= BUFFER_HIGH) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer)
      channel.removeEventListener('bufferedamountlow', ready)
      channel.removeEventListener('close', closed)
      channel.removeEventListener('error', closed)
      signal.removeEventListener('abort', closed)
    }
    const ready = () => { cleanup(); resolve() }
    const closed = () => { cleanup(); reject(new Error('连接已中断。')) }
    const timer = setTimeout(closed, 30000)
    channel.addEventListener('bufferedamountlow', ready, { once: true })
    channel.addEventListener('close', closed, { once: true })
    channel.addEventListener('error', closed, { once: true })
    signal.addEventListener('abort', closed, { once: true })
    if (channel.bufferedAmount <= BUFFER_HIGH) ready()
  })
}

export function gatheredDescription(pc: RTCPeerConnection, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const cleanup = () => { clearTimeout(timer); pc.removeEventListener('icegatheringstatechange', check); signal.removeEventListener('abort', abort) }
    const abort = () => { cleanup(); reject(new Error('建立连接已停止。')) }
    const check = () => {
      if (pc.iceGatheringState === 'complete' && pc.localDescription?.sdp) { cleanup(); resolve(pc.localDescription.sdp) }
    }
    const timer = setTimeout(() => { cleanup(); reject(new Error('收集局域网连接信息超时。')) }, 10000)
    pc.addEventListener('icegatheringstatechange', check)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    else check()
  })
}
