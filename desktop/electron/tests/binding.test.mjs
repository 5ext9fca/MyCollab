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

test('修改同一设备配置可沿用加密令牌，仍核验归属且不回显', async () => {
  const { service, stored } = fixture()
  await service.bind(input)
  const result = await service.bind({ ...input, token: '', model: 'new/model', opencode: '/中文 目录/opencode' })
  assert.equal(result.model, 'new/model')
  assert.equal(result.opencode, '/中文 目录/opencode')
  assert.equal(stored().device_token, input.token)
  assert.equal('device_token' in result, false)
  service.probe = async () => new Response(null, { status: 403 })
  await assert.rejects(service.bind({ ...input, token: '' }), /身份验证失败/)
  assert.equal(stored().model, 'new/model')
})

test('令牌留空不允许跨设备或无绑定配置，并发启动验证拒绝', async () => {
  const { service } = fixture()
  await assert.rejects(service.bind({ ...input, token: '' }), /新的设备令牌/)
  await service.bind(input)
  await assert.rejects(service.bind({ ...input, token: '', deviceId: '22222222-2222-2222-2222-222222222222' }), /新的设备令牌/)
  let release
  service.probe = () => new Promise(resolve => { release = resolve })
  const saving = service.bind({ ...input, token: '' })
  await assert.rejects(service.verified(), /绑定正在处理/)
  while (!release) await new Promise(resolve => setImmediate(resolve))
  release(Response.json({ device_id: id, owner_id: '1', schema_versions: [1] }))
  await saving
})

test('当前身份断网仍可读取自检配置，但启动继续要求在线核验', async () => {
  const { service, transport } = fixture()
  await service.bind(input)
  transport.handle = async () => { throw Error('offline') }
  service.probe = async () => { throw Error('offline') }
  assert.equal((await service.local()).binding.device_token, input.token)
  assert.equal((await service.read()).deviceId, id)
  await assert.rejects(service.verified(), /offline/)
  transport.generation++
  await assert.rejects(service.local(), /身份已改变/)
})

test('本地自检配置不能在首次未核验身份时读取', async () => {
  const { service } = fixture()
  await assert.rejects(service.local(), /先登录/)
})
