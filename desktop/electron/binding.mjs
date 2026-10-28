/** 本地设备绑定必须同时核验业务会话与设备令牌，身份由服务端给出。 */
import { APP_ORIGIN } from './transport.mjs'
import { validateBinding } from './vault.mjs'

/** @param {Response} response */
async function boundedJSON(response) {
  if (!response.ok || !response.body) { await response.body?.cancel(); throw new Error('身份验证失败，请检查登录和设备有效期。') }
  const reader = response.body.getReader()
  const chunks = []
  let length = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      length += value.length
      if (length > 128 * 1024) throw new Error('设备验证响应过大。')
      chunks.push(value)
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } finally { await reader.cancel().catch(() => {}) }
}

/** @param {import('./vault.mjs').RunnerBinding | null} binding */
function publicBinding(binding) {
  return binding ? { deviceId: binding.deviceId, model: binding.model, opencode: binding.opencode } : null
}

export class DeviceBindings {
  /** @param {() => import('./transport.mjs').BusinessTransport | undefined} current
   * @param {import('./vault.mjs').BindingVault} vault
   * @param {typeof fetch} probe */
  constructor(current, vault, probe) { this.current = current; this.vault = vault; this.probe = probe; this.busy = false }

  async identity() {
    const transport = this.current()
    if (!transport || transport.changingIdentity) throw new Error('请先登录协作服务器。')
    const generation = transport.generation
    const user = await boundedJSON(await transport.handle(new Request(APP_ORIGIN + '/api/auth/me/')))
    const owner = String(user?.id)
    if (!/^[1-9][0-9]*$/.test(owner)) throw new Error('登录身份无效。')
    const assertCurrent = () => {
      if (this.current() !== transport || generation !== transport.generation || transport.changingIdentity) {
        throw new Error('登录身份已改变，请重新操作。')
      }
    }
    assertCurrent()
    return { transport, owner, assertCurrent }
  }

  async read() {
    const identity = await this.identity()
    const binding = await this.vault.load(identity.transport.server, identity.owner)
    identity.assertCurrent()
    return publicBinding(binding)
  }

  /** @param {unknown} input */
  async bind(input) {
    if (this.busy) throw new Error('设备绑定正在处理。')
    this.busy = true
    try {
      const identity = await this.identity()
      if (!input || typeof input !== 'object') throw new Error('设备配置无效。')
      const fields = /** @type {Record<string, unknown>} */ (input)
      const binding = validateBinding({ server: identity.transport.server, owner: identity.owner,
        deviceId: fields.deviceId, device_token: fields.token, model: fields.model, opencode: fields.opencode })
      if (!/^[\x21-\x7e]{1,128}$/.test(binding.device_token)) throw new Error('设备令牌格式无效。')
      // 只访问固定设备探测接口；绝不携带业务 Cookie，也不跟随重定向。
      const status = await boundedJSON(await this.probe(binding.server + '/api/agent-runner/status/', {
        method: 'POST', headers: { Authorization: 'Bearer ' + binding.device_token, 'Content-Type': 'application/json' },
        body: '{}', credentials: 'omit', redirect: 'error', signal: AbortSignal.timeout(15_000),
      }))
      if (status.device_id !== binding.deviceId || String(status.owner_id) !== binding.owner ||
          !Array.isArray(status.schema_versions) || !status.schema_versions.includes(1)) {
        throw new Error('设备令牌不属于当前用户或所选设备，请重新创建。')
      }
      identity.assertCurrent()
      await this.vault.save(binding)
      identity.assertCurrent()
      return publicBinding(binding)
    } finally { this.busy = false }
  }
}
