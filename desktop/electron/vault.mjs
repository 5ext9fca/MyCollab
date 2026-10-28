/** 设备配置由系统密钥加密，身份键不含令牌；只由主进程使用。 */
import { createHash, randomUUID } from 'node:crypto'
import { mkdir, open, rename, rm } from 'node:fs/promises'
import path from 'node:path'
import { serverOrigin } from './transport.mjs'

/** @typedef {{server: string, owner: string, deviceId: string, device_token: string, model: string, opencode: string}} RunnerBinding */
const LIMIT = 128 * 1024

/** @param {unknown} input @returns {RunnerBinding} */
export function validateBinding(input) {
  if (!input || typeof input !== 'object') throw new Error('设备配置无效。')
  const value = /** @type {Record<string, unknown>} */ (input)
  for (const key of ['server', 'owner', 'deviceId', 'device_token', 'model', 'opencode']) {
    if (typeof value[key] !== 'string' || !value[key].trim() || value[key].length > 4096 || /[\x00-\x1f\x7f]/.test(value[key])) {
      throw new Error('设备配置字段无效。')
    }
  }
  const binding = /** @type {RunnerBinding} */ (input)
  if (!/^[1-9][0-9]*$/.test(binding.owner) || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(binding.deviceId)) {
    throw new Error('设备身份无效。')
  }
  // 只保留固定字段，避免把供应商凭据或任意附加配置交给 Runner。
  const result = { server: serverOrigin(binding.server), owner: binding.owner, deviceId: binding.deviceId,
    device_token: binding.device_token, model: binding.model, opencode: binding.opencode }
  if (Buffer.byteLength(JSON.stringify(result)) > 30 * 1024) throw new Error('设备配置过大。')
  return result
}

export class BindingVault {
  /** @param {string} directory
   * @param {Pick<import('electron').SafeStorage, 'isAsyncEncryptionAvailable' | 'encryptStringAsync' | 'decryptStringAsync'>} encryption */
  constructor(directory, encryption) { this.directory = directory; this.encryption = encryption }

  /** @param {string} server @param {string} owner */
  filename(server, owner) {
    if (!/^[1-9][0-9]*$/.test(owner)) throw new Error('用户身份无效。')
    const key = createHash('sha256').update(serverOrigin(server) + '\0' + owner).digest('hex')
    return path.join(this.directory, key + '.encrypted')
  }

  async ready() {
    if (!(await this.encryption.isAsyncEncryptionAvailable())) throw new Error('系统凭据保护暂不可用，请解锁系统钥匙串后重试。')
  }

  /** @param {RunnerBinding} input */
  async save(input) {
    const binding = validateBinding(input)
    await this.ready()
    const encrypted = await this.encryption.encryptStringAsync(JSON.stringify(binding))
    if (!encrypted.length || encrypted.length > LIMIT) throw new Error('加密设备配置大小无效。')
    await mkdir(this.directory, { recursive: true, mode: 0o700 })
    const filename = this.filename(binding.server, binding.owner)
    const temporary = filename + '.' + randomUUID()
    try {
      const file = await open(temporary, 'wx', 0o600)
      try { await file.writeFile(encrypted); await file.sync() } finally { await file.close() }
      await rename(temporary, filename)
    } finally { await rm(temporary, { force: true }) }
  }

  /** @param {string} server @param {string} owner @returns {Promise<RunnerBinding | null>} */
  async load(server, owner) {
    const filename = this.filename(server, owner)
    let file
    try { file = await open(filename, 'r') }
    catch (error) { if (/** @type {NodeJS.ErrnoException} */ (error).code === 'ENOENT') return null; throw error }
    let encrypted
    try {
      const stat = await file.stat()
      if (!stat.isFile() || stat.size > LIMIT) throw new Error('加密设备配置格式无效。')
      const buffer = Buffer.alloc(LIMIT + 1)
      const { bytesRead } = await file.read(buffer, 0, buffer.length, 0)
      if (bytesRead !== stat.size || bytesRead > LIMIT) throw new Error('加密设备配置读取失败。')
      encrypted = buffer.subarray(0, bytesRead)
    } finally { await file.close() }
    await this.ready()
    const decrypted = await this.encryption.decryptStringAsync(encrypted)
    let binding
    try { binding = validateBinding(JSON.parse(decrypted.result)) }
    catch { throw new Error('设备配置无法读取，请重新绑定。') }
    if (binding.server !== serverOrigin(server) || binding.owner !== owner) throw new Error('设备配置不属于当前身份。')
    if (decrypted.shouldReEncrypt) await this.save(binding)
    return binding
  }

  /** @param {string} server @param {string} owner */
  async remove(server, owner) { await rm(this.filename(server, owner), { force: true }) }
}
