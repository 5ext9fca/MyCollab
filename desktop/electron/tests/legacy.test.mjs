import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, writeFile, chmod, readFile, rm, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { readLegacyConfig } from '../legacy.mjs'
import { DeviceBindings } from '../binding.mjs'
import { RunnerController } from '../runner.mjs'
const id = '11111111-1111-1111-1111-111111111111'
const config = { server: 'https://example.com', device_token: 'legacy-secret', model: 'provider/model', opencode: '/中文 路径/opencode' }
async function fixture(t) {
  const directory = await mkdtemp(path.join(tmpdir(), 'legacy-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const filename = path.join(directory, 'runner.json')
  await writeFile(filename, JSON.stringify(config), { mode: 0o600 })
  return filename
}

test('导入拒绝公开权限、符号链接、自定义 CA 与超大配置', { skip: process.platform === 'win32' }, async t => {
  const filename = await fixture(t)
  await chmod(filename, 0o644)
  await assert.rejects(readLegacyConfig(filename), /仅本人/)
  await chmod(filename, 0o600)
  const link = filename + '.link'
  await symlink(filename, link)
  await assert.rejects(readLegacyConfig(link))
  await writeFile(filename, JSON.stringify({ ...config, ca_file: '/custom.pem' }))
  await assert.rejects(readLegacyConfig(filename), /自定义 CA/)
  await writeFile(filename, 'x'.repeat(32769))
  await assert.rejects(readLegacyConfig(filename))
})

test('导入核验服务器和归属，不覆盖现有绑定，保留原文件和共享锁路径', { skip: process.platform === 'win32' }, async t => {
  const filename = await fixture(t)
  let stored = null
  const transport = { server: config.server, generation: 0, changingIdentity: false, handle: async () => Response.json({ id: 1 }) }
  let owner = '2'
  const bindings = new DeviceBindings(() => transport, { load: async () => stored, save: async value => { stored = value } }, async (_url, options) => {
    assert.equal(options.credentials, 'omit')
    assert.equal(options.headers.Authorization, 'Bearer legacy-secret')
    return Response.json({ owner_id: owner, device_id: id, schema_versions: [1] })
  })
  await assert.rejects(bindings.importLegacy(filename), /不属于/)
  owner = '1'
  transport.server = 'https://other.test'
  await assert.rejects(bindings.importLegacy(filename), /对应的服务器/)
  transport.server = config.server
  const summary = await bindings.importLegacy(filename)
  assert.deepEqual(summary, { deviceId: id, model: config.model, opencode: config.opencode })
  assert.equal(stored.legacyState, true)
  assert.deepEqual(JSON.parse(await readFile(filename, 'utf8')), config)
  await assert.rejects(bindings.importLegacy(filename), /不能覆盖/)
  await bindings.bind({ deviceId: id, token: '', model: 'new/model', opencode: 'opencode' })
  assert.equal(stored.legacyState, true)
  const runner = new RunnerController(['unused'], '/new/config.json', async () => ({ binding: stored, assertCurrent() {} }), filename)
  assert.equal(runner.stateConfig(stored), filename)
  assert.equal(runner.stateConfig({ ...stored, legacyState: false }), '/new/config.json')
})
