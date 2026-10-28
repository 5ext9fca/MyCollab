import { test } from 'node:test'
import assert from 'node:assert/strict'
import { DeviceBindings } from '../binding.mjs'
const id = '11111111-1111-1111-1111-111111111111'
const input = { deviceId: id, token: 'private-device-secret', model: 'provider/model', opencode: 'opencode' }
function fixture() {
  const transport = { server: 'https://example.com', generation: 0, changingIdentity: false,
    handle: async () => Response.json({ id: 1 }) }
  let stored = null
  const vault = { save: async value => { stored = value }, load: async () => stored }
  const probe = async (url, options) => {
    assert.equal(url, 'https://example.com/api/agent-runner/status/')
    assert.equal(options.credentials, 'omit')
    assert.equal(options.redirect, 'error')
    assert.equal(options.headers.Authorization, 'Bearer private-device-secret')
    return Response.json({ device_id: id, owner_id: '1', schema_versions: [1] })
  }
  return { transport, vault, service: new DeviceBindings(() => transport, vault, probe), stored: () => stored }
}

test('绑定从服务端获取身份，返回值不含令牌且不信任页面提供的用户和服务器', async () => {
  const { service, stored } = fixture()
  const result = await service.bind({ ...input, owner: '2', server: 'https://evil.test' })
  assert.deepEqual(result, { deviceId: id, model: 'provider/model', opencode: 'opencode' })
  assert.equal(stored().owner, '1')
  assert.equal(stored().server, 'https://example.com')
  assert.equal(stored().device_token, input.token)
  assert.deepEqual(await service.read(), result)
})

test('拒绝他人的有效令牌、另一设备令牌以及旧版不提供身份的服务', async () => {
  for (const status of [{ device_id: id, owner_id: '2' }, { device_id: 'other', owner_id: '1' }, {}]) {
    const { service, stored } = fixture()
    service.probe = async () => Response.json({ schema_versions: [1], ...status })
    await assert.rejects(service.bind(input), /不属于/)
    assert.equal(stored(), null)
  }
})

test('探测期间切换账户则不保存，不把旧绑定返回新页面', async () => {
  const { service, transport, stored } = fixture()
  service.probe = async () => {
    transport.generation++
    return Response.json({ device_id: id, owner_id: '1', schema_versions: [1] })
  }
  await assert.rejects(service.bind(input), /身份已改变/)
  assert.equal(stored(), null)
})

test('拒绝未登录请求以及超过大小上限的设备响应', async () => {
  const { service, transport, stored } = fixture()
  transport.handle = async () => new Response(null, { status: 403 })
  await assert.rejects(service.bind(input), /身份验证失败/)
  transport.handle = async () => Response.json({ id: 1 })
  service.probe = async () => new Response('x'.repeat(128 * 1024 + 1))
  await assert.rejects(service.bind(input), /响应过大/)
  assert.equal(stored(), null)
})
