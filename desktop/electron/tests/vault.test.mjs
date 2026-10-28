import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { BindingVault, validateBinding } from '../vault.mjs'

const binding = { server: 'https://example.com', owner: '1', deviceId: '11111111-1111-1111-1111-111111111111',
  device_token: 'private-device-secret', model: 'provider/model', opencode: '/中文 路径/opencode' }
async function fixture(t) {
  const directory = await mkdtemp(path.join(tmpdir(), 'mycollab-vault-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const key = randomBytes(32)
  const encryption = {
    isAsyncEncryptionAvailable: async () => true,
    encryptStringAsync: async value => {
      const iv = randomBytes(12), cipher = createCipheriv('aes-256-gcm', key, iv)
      const body = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()])
      return Buffer.concat([iv, cipher.getAuthTag(), body])
    },
    decryptStringAsync: async value => {
      const decipher = createDecipheriv('aes-256-gcm', key, value.subarray(0, 12))
      decipher.setAuthTag(value.subarray(12, 28))
      return { result: Buffer.concat([decipher.update(value.subarray(28)), decipher.final()]).toString(), shouldReEncrypt: false }
    },
  }
  return { vault: new BindingVault(directory, encryption), encryption }
}

test('加密保存和读取按服务器及账户隔离，不落盘明文凭据', async t => {
  const { vault } = await fixture(t)
  await vault.save(binding)
  const bytes = await readFile(vault.filename(binding.server, binding.owner))
  assert.equal(bytes.includes(Buffer.from(binding.device_token)), false)
  assert.deepEqual(await vault.load(binding.server, binding.owner), binding)
  assert.equal(await vault.load(binding.server, '2'), null)
  assert.equal(await vault.load('https://other.test', '1'), null)
  await vault.remove(binding.server, binding.owner)
  assert.equal(await vault.load(binding.server, binding.owner), null)
})

test('系统保护不可用时保留旧配置，不回退明文', async t => {
  const { vault, encryption } = await fixture(t)
  await vault.save(binding)
  encryption.isAsyncEncryptionAvailable = async () => false
  await assert.rejects(vault.save({ ...binding, device_token: 'replacement' }), /暂不可用/)
  encryption.isAsyncEncryptionAvailable = async () => true
  assert.deepEqual(await vault.load(binding.server, binding.owner), binding)
})

test('拒绝复制到其他身份的密文及被篡改配置', async t => {
  const { vault } = await fixture(t)
  await vault.save(binding)
  const encrypted = await readFile(vault.filename(binding.server, '1'))
  await writeFile(vault.filename(binding.server, '2'), encrypted)
  await assert.rejects(vault.load(binding.server, '2'), /不属于当前身份/)
  encrypted[30] ^= 1
  await writeFile(vault.filename(binding.server, '1'), encrypted)
  await assert.rejects(vault.load(binding.server, '1'))
})

test('固定配置字段过滤额外凭据并拒绝不安全服务器和控制字符', () => {
  assert.deepEqual(validateBinding({ ...binding, provider_token: 'never-forward' }), binding)
  for (const invalid of [{ server: 'http://example.com' }, { owner: '../../other' }, { device_token: 'x\nsecret' }, { deviceId: 'other' }]) {
    assert.throws(() => validateBinding({ ...binding, ...invalid }))
  }
})

test('系统密钥轮换后重新加密且保留同一设备身份', async t => {
  const { vault, encryption } = await fixture(t)
  await vault.save(binding)
  const before = await readFile(vault.filename(binding.server, '1'))
  const decrypt = encryption.decryptStringAsync
  encryption.decryptStringAsync = async value => ({ ...await decrypt(value), shouldReEncrypt: true })
  assert.deepEqual(await vault.load(binding.server, '1'), binding)
  const after = await readFile(vault.filename(binding.server, '1'))
  assert.notDeepEqual(after, before)
  assert.deepEqual(await vault.load(binding.server, '1'), binding)
})
