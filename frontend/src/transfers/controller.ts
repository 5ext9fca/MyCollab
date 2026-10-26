import { createTransfer, joinTransfer, operateTransfer, type TransferSession } from '../api/transfers'
import { CHUNK_BYTES, FileReceiver, gatheredDescription, MAX_FILE_BYTES, newToken, sha256, waitForBuffer } from './protocol'

export interface TransferState {
  session: TransferSession | null
  busy: boolean
  active: boolean
  message: string
  bytes: number
  checksum: string
  downloadUrl: string
  success: boolean
}
const terminal = new Set(['completed', 'failed', 'cancelled', 'expired'])
const errors: Record<string, string> = {
  checksum_mismatch: 'SHA-256 校验不一致，文件已丢弃。', connection_failed: '无法建立直连或连接中断，请检查浏览器及系统的局域网访问权限、防火墙和网络。',
  protocol_error: '传输数据格式或大小无效。', timeout: '传输超时，请重新发送。', local_error: '本地处理文件失败，请重新发送。',
}

/** 每个页面独立持有凭据和连接；凭据不写入浏览器持久存储。 */
export class TransferController {
  readonly state: TransferState = { session: null, busy: false, active: false, message: '', bytes: 0, checksum: '', downloadUrl: '', success: false }
  private token = newToken()
  private stop = new AbortController()
  private sendData: ArrayBuffer | null = null
  private lastProgressPaint = 0
  private pc: RTCPeerConnection | null = null
  private channel: RTCDataChannel | null = null
  private receiver: FileReceiver | null = null
  private timer: ReturnType<typeof setTimeout> | undefined
  private connecting = false
  private sentEnd = false
  private receivingEnd = false
  private lastActivity = Date.now()
  private pollErrors = 0
  private disposed = false

  private changed: (state: TransferState) => void
  constructor(changed: (state: TransferState) => void) { this.changed = changed; this.emit() }
  private emit() { if (!this.disposed) this.changed({ ...this.state, session: this.state.session ? { ...this.state.session } : null }) }
  private emitProgress() {
    if (Date.now() - this.lastProgressPaint >= 100) { this.lastProgressPaint = Date.now(); this.emit() }
  }
  private get alive() { return !this.stop.signal.aborted && !this.disposed }

  async send(file: File) {
    this.state.busy = this.state.active = true
    this.state.message = '正在计算发送文件的 SHA-256…'
    this.emit()
    try {
      if (file.size > MAX_FILE_BYTES) throw new Error('单文件不得超过 100 MiB。')
      const data = await file.arrayBuffer()
      const checksum = await sha256(data)
      if (!this.alive) return
      this.sendData = data
      this.state.checksum = checksum
      const session = await createTransfer({ name: file.name, size: file.size, sha256: checksum }, this.token)
      if (!this.alive) { void operateTransfer(session.id, this.token, 'cancel').catch(() => {}); return }
      this.state.session = session
      this.state.message = '请将配对码交给接收方，5 分钟内完成配对并确认接收。'
      this.schedule()
    } catch (error) { this.localFailure(error) }
    finally { this.state.busy = false; this.emit() }
  }

  async join(code: string) {
    this.state.busy = this.state.active = true
    this.state.message = '正在配对…'
    this.emit()
    try {
      const session = await joinTransfer(code.trim().toUpperCase(), this.token)
      if (!this.alive) { void operateTransfer(session.id, this.token, 'cancel').catch(() => {}); return }
      this.state.session = session
      this.state.message = '请核对发送人和文件信息，再确认接收。'
      this.schedule()
    } catch (error) { this.localFailure(error) }
    finally { this.state.busy = false; this.emit() }
  }

  async accept() {
    const session = this.state.session
    if (!session || this.state.busy || session.status !== 'paired') return
    this.state.busy = true
    this.emit()
    try {
      await operateTransfer(session.id, this.token, 'accept')
      if (this.alive) this.schedule(0)
    } catch (error) { this.localFailure(error) }
    finally { this.state.busy = false; this.emit() }
  }

  private schedule(delay = 1000) {
    if (!this.alive) return
    clearTimeout(this.timer)
    this.timer = setTimeout(() => { void this.poll() }, delay)
  }

  private async poll() {
    const session = this.state.session
    if (!session || !this.alive) return
    try {
      let result = await operateTransfer(session.id, this.token)
      if (this.alive && result.status === 'accepted' && this.state.downloadUrl && this.state.checksum) {
        result = await operateTransfer(session.id, this.token, 'complete', { sha256: this.state.checksum })
      }
      if (!this.alive) return
      this.pollErrors = 0
      await this.apply(result)
      if (this.alive && result.status === 'accepted' && Date.now() - this.lastActivity > 60000) { this.fail('timeout'); return }
      this.schedule()
    } catch (error) {
      if (!this.alive) return
      if (++this.pollErrors >= 4) { this.localFailure(error); return }
      this.state.message = '连接信息暂时不可用，正在重试…'
      this.emit()
      this.schedule(1000 * 2 ** this.pollErrors)
    }
  }

  private async apply(session: TransferSession) {
    if (!this.alive) return
    const previousStatus = this.state.session?.status
    this.state.session = { ...session, code: this.state.session?.code }
    if (terminal.has(session.status)) {
      if (session.status === 'completed') {
        if (session.received_sha256 !== session.sha256 || (session.role === 'receiver' && !this.state.downloadUrl)) { this.fail('protocol_error'); return }
        this.state.success = true
        this.state.message = session.role === 'sender' ? '传输成功：接收端 SHA-256 校验一致。' : 'SHA-256 校验一致，可以保存文件。'
        this.state.bytes = session.size
      } else {
        this.state.message = session.status === 'cancelled' ? '传输已取消。' : session.status === 'expired' ? '传输会话已过期，请重新配对。' : errors[session.error] || '传输失败，请重新发送。'
        this.revokeDownload()
      }
      this.state.active = false
      this.release()
      this.emit()
      return
    }
    if (session.status === 'paired' && session.role === 'sender') this.state.message = '已配对，等待接收方确认。'
    if (session.status === 'accepted') {
      if (previousStatus !== 'accepted') { this.lastActivity = Date.now(); this.state.message = '正在建立局域网直连…' }
      if (!this.pc && !this.connecting && (session.role === 'sender' || session.offer)) {
        this.connecting = true
        try { await this.connect(session) }
        catch { if (this.alive) this.fail('connection_failed') }
        finally { this.connecting = false }
      }
      if (this.pc && session.role === 'sender' && session.answer && !this.pc.remoteDescription) {
        try { await this.pc.setRemoteDescription({ type: 'answer', sdp: session.answer }) }
        catch { if (this.alive) this.fail('connection_failed') }
      }
    }
    this.emit()
  }

  private async connect(session: TransferSession) {
    const pc = new RTCPeerConnection({ iceServers: [] })
    this.pc = pc
    pc.onconnectionstatechange = () => {
      if (!this.alive) return
      if (pc.connectionState === 'failed') this.fail('connection_failed')
    }
    if (session.role === 'sender') {
      this.bindChannel(pc.createDataChannel('mycollab-file-v1', { ordered: true }), 'sender')
      await pc.setLocalDescription(await pc.createOffer())
      const sdp = await gatheredDescription(pc, this.stop.signal)
      if (!this.alive) return
      await operateTransfer(session.id, this.token, 'offer', { sdp })
    } else {
      this.receiver = new FileReceiver(session.size, session.sha256)
      pc.ondatachannel = (event) => {
        if (this.channel || event.channel.label !== 'mycollab-file-v1' || !event.channel.ordered || event.channel.maxRetransmits !== null || event.channel.maxPacketLifeTime !== null) { event.channel.close(); this.fail('protocol_error'); return }
        this.bindChannel(event.channel, 'receiver')
      }
      await pc.setRemoteDescription({ type: 'offer', sdp: session.offer })
      await pc.setLocalDescription(await pc.createAnswer())
      const sdp = await gatheredDescription(pc, this.stop.signal)
      if (!this.alive) return
      await operateTransfer(session.id, this.token, 'answer', { sdp })
    }
  }

  private bindChannel(channel: RTCDataChannel, role: 'sender' | 'receiver') {
    this.channel = channel
    channel.binaryType = 'arraybuffer'
    channel.bufferedAmountLowThreshold = 128 * 1024
    channel.onopen = () => {
      if (!this.alive) return
      this.lastActivity = Date.now()
      this.state.message = role === 'sender' ? '正在发送…' : '正在接收…'
      this.emit()
      if (role === 'sender') void this.sendChunks()
    }
    channel.onmessage = (event) => {
      if (!this.alive) return
      if (role !== 'receiver') { this.fail('protocol_error'); return }
      this.lastActivity = Date.now()
      if (event.data === 'end' && !this.receivingEnd) {
        this.receivingEnd = true
        void this.verify()
      } else {
        try {
          this.receiver!.append(event.data)
          this.state.bytes = this.receiver!.bytes
          this.emitProgress()
        } catch { this.fail('protocol_error') }
      }
    }
    channel.onerror = () => { if (this.alive && !this.sentEnd && !this.receivingEnd) this.fail('connection_failed') }
    channel.onclose = () => { if (this.alive && !this.sentEnd && !this.receivingEnd) this.fail('connection_failed') }
  }

  private async sendChunks() {
    try {
      const data = this.sendData!
      const channel = this.channel!
      for (let offset = 0; offset < data.byteLength; offset += CHUNK_BYTES) {
        await waitForBuffer(channel, this.stop.signal)
        if (!this.alive) return
        const chunk = data.slice(offset, offset + CHUNK_BYTES)
        channel.send(chunk)
        this.state.bytes = offset + chunk.byteLength
        this.lastActivity = Date.now()
        this.emitProgress()
      }
      await waitForBuffer(channel, this.stop.signal)
      if (!this.alive) return
      channel.send('end')
      this.sentEnd = true
      this.sendData = null
      this.state.message = '文件已发送，等待接收端 SHA-256 校验…'
      this.emit()
    } catch { if (this.alive) this.fail('connection_failed') }
  }

  private async verify() {
    this.state.message = '已收到文件，正在独立计算 SHA-256…'
    this.emit()
    try {
      const result = await this.receiver!.finish()
      if (!this.alive) return
      this.state.checksum = result.checksum
      this.state.downloadUrl = URL.createObjectURL(result.blob)
      const session = await operateTransfer(this.state.session!.id, this.token, 'complete', { sha256: result.checksum })
      if (this.alive) await this.apply(session)
    } catch (error) {
      if (!this.alive) return
      if (error instanceof Error && error.message.includes('SHA-256')) this.fail('checksum_mismatch')
      else if (this.state.downloadUrl) {
        // 确认响应可能丢失；轮询服务器终态，不重复传输文件。
        this.state.message = '本地 SHA-256 已一致，正在确认传输结果…'
        this.emit()
      } else this.fail('protocol_error')
    }
  }

  private localFailure(error: unknown) {
    if (!this.alive) return
    this.state.message = error instanceof Error ? error.message : '操作失败，请重新开始。'
    this.fail('local_error', true)
  }

  private fail(error: string, keepMessage = false) {
    if (!this.alive) return
    if (!keepMessage) this.state.message = errors[error] || '传输失败。'
    const session = this.state.session
    this.state.active = this.state.busy = false
    this.revokeDownload()
    this.release()
    this.emit()
    if (session) void operateTransfer(session.id, this.token, 'fail', { error }).catch(() => {})
  }

  cancel() {
    if (!this.alive) return
    const session = this.state.session
    this.state.active = this.state.busy = false
    this.state.message = '传输已取消。'
    this.revokeDownload()
    this.release()
    this.emit()
    if (session) void operateTransfer(session.id, this.token, 'cancel').catch(() => {})
  }

  private release() {
    this.stop.abort()
    clearTimeout(this.timer)
    if (this.channel) { this.channel.onclose = this.channel.onerror = this.channel.onmessage = this.channel.onopen = null; this.channel.close() }
    if (this.pc) { this.pc.onconnectionstatechange = this.pc.ondatachannel = null; this.pc.close() }
    this.channel = null
    this.pc = null
    this.receiver?.clear()
    this.receiver = null
    this.sendData = null
  }
  private revokeDownload() { if (this.state.downloadUrl) URL.revokeObjectURL(this.state.downloadUrl); this.state.downloadUrl = '' }
  dispose() { this.cancel(); this.disposed = true; this.release(); this.revokeDownload() }
}
