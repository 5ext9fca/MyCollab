/** 桌面只管理本机 Runner，命令与状态路径由宿主固定，凭据只走匿名管道。 */
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { open } from 'node:fs/promises'
import path from 'node:path'

/** @typedef {import('./vault.mjs').RunnerBinding} Binding */
/** @typedef {{binding: Binding, assertCurrent: () => void}} Verified */

export class RunnerController {
  /** @param {string[]} command @param {string} configPath @param {() => Promise<Verified>} resolve */
  constructor(command, configPath, resolve) {
    this.command = command; this.configPath = configPath; this.resolve = resolve
    /** @type {import('node:child_process').ChildProcessWithoutNullStreams | null} */
    this.child = null
    /** @type {Verified | null} */
    this.identity = null
    /** @type {Promise<void> | null} */
    this.exited = null
    /** @type {import('node:child_process').ChildProcessWithoutNullStreams | null} */
    this.diagnostic = null
    /** @type {Promise<void> | null} */
    this.diagnosticExited = null
    this.diagnosing = false
    this.epoch = 0; this.starting = false; this.lastError = ''
  }

  /** @param {Binding} binding @param {string[]} flags */
  launch(binding, flags) {
    /** @type {NodeJS.ProcessEnv} */
    const env = { ...process.env, PYTHONIOENCODING: 'utf-8' }
    for (const key of Object.keys(env)) if (key.startsWith('MYCOLLAB_')) delete env[key]
    const child = spawn(this.command[0], [...this.command.slice(1), '--config', this.configPath,
      '--config-stdin', '--parent-pid', String(process.pid), ...flags], {
      windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env,
    })
    child.stdin.on('error', () => {})
    // 不保存、不转发 Runner 日志，避免配置错误将秘密带到页面。
    child.stderr.resume()
    const payload = JSON.stringify({ server: binding.server, device_token: binding.device_token,
      model: binding.model, opencode: binding.opencode }) + '\n'
    return { child, payload }
  }

  async start() {
    if (this.child || this.starting || this.diagnostic || this.diagnosing) throw new Error('Runner 已在运行或启动中。')
    this.starting = true
    this.lastError = ''
    const epoch = ++this.epoch
    try {
      const identity = await this.resolve()
      identity.assertCurrent()
      if (epoch !== this.epoch) throw new Error('启动已取消。')
      const { child, payload } = this.launch(identity.binding, ['--control-stdin', '--desktop-events'])
      this.child = child; this.identity = identity
      this.exited = new Promise(resolve => {
        child.once('close', code => {
          if (this.child === child) {
            this.child = null
            if (code !== 0 && code !== 130) this.lastError = 'Runner 已异常退出，请自检后重新启动。'
          }
          resolve()
        })
      })
      await new Promise((resolve, reject) => {
        let pending = ''
        let ready = false
        const timer = setTimeout(() => finish(new Error('Runner 启动超时。')), 15_000)
        /** @param {Error | undefined} [error] */
        const finish = error => {
          clearTimeout(timer)
          if (ready) return
          ready = true
          if (error) reject(error); else resolve(undefined)
        }
        child.once('error', () => finish(new Error('无法启动内置 Runner，请检查安装包。')))
        child.once('close', () => finish(new Error('Runner 未能取得设备锁或配置不可用。')))
        child.stdout.on('data', chunk => {
          if (ready) return
          pending += chunk.toString('utf8')
          if (pending.length > 16384) { finish(new Error('Runner 启动响应无效。')); return }
          const lines = pending.split('\n'); pending = lines.pop() || ''
          for (const line of lines) {
            try { if (JSON.parse(line).event === 'ready') finish() } catch { /* 忽略脱敏文本提示。 */ }
          }
        })
        child.once('spawn', () => {
          if (epoch !== this.epoch) { child.stdin.end(); finish(new Error('启动已取消。')); return }
          child.stdin.write(payload)
        })
      })
      identity.assertCurrent()
      if (epoch !== this.epoch) throw new Error('启动已取消。')
      this.starting = false
      return await this.status()
    } catch (error) {
      await this.stop()
      throw error
    } finally { this.starting = false }
  }

  async stop() {
    this.epoch++
    const child = this.child
    const diagnostic = this.diagnostic
    if (!child && !diagnostic) { this.identity = null; return }
    child?.stdin.end()
    diagnostic?.stdin.end()
    /** @type {ReturnType<typeof setTimeout> | undefined} */
    let timer
    try {
      await Promise.race([Promise.all([this.exited, this.diagnosticExited]), new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Runner 尚未停止，请稍后重试；没有切换身份。')), 20_000)
      })])
      if (this.child === child) this.child = null
      this.identity = null
    } finally { clearTimeout(timer) }
  }

  async status() {
    const state = this.child ? (this.starting ? 'starting' : 'running') : 'stopped'
    const result = { state, pending_results: 0, rejected_results: 0, error: this.lastError }
    const identity = this.identity
    if (!identity) return result
    identity.assertCurrent()
    const { binding } = identity
    const key = createHash('sha256').update(binding.server.replace(/\/$/, '') + '\0' + binding.device_token).digest('hex')
    let file
    try {
      file = await open(path.join(path.dirname(this.configPath), 'runner-state', key, 'status.json'), 'r')
      const buffer = Buffer.alloc(8193)
      const { bytesRead } = await file.read(buffer, 0, buffer.length, 0)
      if (bytesRead > 8192) throw new Error("状态文件过大。")
      const data = JSON.parse(buffer.subarray(0, bytesRead).toString('utf8'))
      identity.assertCurrent()
      if (this.child && ['starting', 'running', 'delivering', 'idle', 'offline', 'unauthorized', 'expired'].includes(data.state)) result.state = data.state
      for (const field of /** @type {const} */ (['pending_results', 'rejected_results'])) {
        if (Number.isInteger(data[field]) && data[field] >= 0 && data[field] <= 100) result[field] = data[field]
      }
    } catch { /* 文件可能正在原子替换；进程状态仍由宿主管理。 */ }
    finally { await file?.close() }
    identity.assertCurrent()
    return result
  }

  async diagnose() {
    if (this.child || this.starting || this.diagnostic || this.diagnosing) throw new Error('请先停止 Runner，再进行自检。')
    this.diagnosing = true
    const epoch = this.epoch
    try {
      const identity = await this.resolve()
      identity.assertCurrent()
      if (epoch !== this.epoch) throw new Error('自检已取消。')
      const { child, payload } = this.launch(identity.binding, ['--diagnose', '--control-stdin'])
      this.diagnostic = child
      this.diagnosticExited = new Promise(resolve => child.once('close', () => {
        if (this.diagnostic === child) this.diagnostic = null
        resolve()
      }))
      return await new Promise((resolve, reject) => {
        let output = '', overflow = false
        const timer = setTimeout(() => { child.stdin.end(); reject(new Error('自检超时，请等待停止后重试。')) }, 40_000)
        child.once('error', () => { clearTimeout(timer); reject(new Error('无法运行内置自检。')) })
        child.stdout.on('data', chunk => {
          if (overflow) return
          output += chunk.toString('utf8')
          if (output.length > 16384) { output = ''; overflow = true; child.stdin.end() }
        })
        child.once('spawn', () => {
          if (epoch !== this.epoch) child.stdin.end()
          else child.stdin.write(payload)
        })
        child.once('close', code => {
          clearTimeout(timer)
          try {
            identity.assertCurrent()
            if (code !== 0 || overflow || epoch !== this.epoch) throw new Error('自检失败。')
            const value = JSON.parse(output)
            const allowed = ['ok', 'unavailable', 'incompatible', 'unauthorized']
            if (!allowed.includes(value.opencode) || !allowed.includes(value.server)) throw new Error('自检响应无效。')
            resolve({ opencode: value.opencode, server: value.server, protocol: value.protocol === 1 ? 1 : 0 })
          } catch { reject(new Error('自检失败或登录身份已经变化。')) }
        })
      })
    } finally { this.diagnosing = false }
  }
}
