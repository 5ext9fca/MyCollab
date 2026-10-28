/** 只读取宿主指定的旧 macOS 配置；不删除原配置或复制待发箱。 */
import { constants } from 'node:fs'
import { open } from 'node:fs/promises'
import { serverOrigin } from './transport.mjs'

/** @param {string} filename */
export async function readLegacyConfig(filename) {
  const file = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW)
  try {
    const stat = await file.stat()
    if (!stat.isFile() || stat.size > 32768 || stat.uid !== process.getuid?.() || (stat.mode & 0o077)) {
      throw new Error('旧配置必须属于当前用户且仅本人可读写。')
    }
    const buffer = Buffer.alloc(32769)
    const { bytesRead } = await file.read(buffer, 0, buffer.length, 0)
    if (bytesRead !== stat.size || bytesRead > 32768) throw new Error('旧配置读取失败。')
    let value
    try { value = JSON.parse(buffer.subarray(0, bytesRead).toString('utf8')) }
    catch { throw new Error('旧配置格式无效。') }
    if (!value || typeof value !== 'object') throw new Error('旧配置格式无效。')
    // 自定义 CA 尚未接入新宿主；禁止导入后悄悄改变证书信任行为。
    if (value.ca_file) throw new Error('此旧配置使用自定义 CA，暂不能导入。')
    if (typeof value.device_token !== 'string' || !/^[\x21-\x7e]{1,128}$/.test(value.device_token)) {
      throw new Error('旧配置设备令牌无效。')
    }
    return { server: serverOrigin(value.server), token: value.device_token,
      model: value.model, opencode: value.opencode || 'opencode' }
  } finally { await file.close() }
}
