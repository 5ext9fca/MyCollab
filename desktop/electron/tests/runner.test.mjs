import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { RunnerController } from '../runner.mjs'

const binding = { server: 'https://example.com', owner: '1', deviceId: 'device',
  device_token: 'private-test-token', model: 'test', opencode: 'opencode' }
async function fixture(t, resolve = async () => ({ binding, assertCurrent() {} })) {
  const directory = await mkdtemp(path.join(tmpdir(), '桌面 Runner '))
  const script = fileURLToPath(new URL('./fixtures/runner.mjs', import.meta.url))
  const runner = new RunnerController([process.execPath, script], path.join(directory, 'config.json'), resolve)
  t.after(async () => { await runner.stop(); await rm(directory, { recursive: true, force: true }) })
  return runner
}

test('就绪事件后启动成功，重复启动拒绝，EOF 等待真实进程退出', async t => {
  const runner = await fixture(t)
  assert.equal((await runner.start()).state, 'running')
  assert.equal((await runner.status()).state, 'running')
  await assert.rejects(runner.start(), /已在运行/)
  await assert.rejects(runner.diagnose(), /先停止/)
  const child = runner.child
  await runner.stop()
  assert.equal(child.exitCode, 130)
  assert.equal((await runner.status()).state, 'stopped')
})

test('身份验证期间停止会取消启动，不能在退出后创建进程', async t => {
  let release
  const runner = await fixture(t, () => new Promise(resolve => { release = resolve }))
  const starting = runner.start()
  await runner.stop()
  release({ binding, assertCurrent() {} })
  await assert.rejects(starting, /取消/)
  assert.equal(runner.child, null)
})

test('自检只返回固定字段，不泄漏原始输出中的令牌', async t => {
  const runner = await fixture(t)
  assert.deepEqual(await runner.diagnose(), { opencode: 'ok', server: 'ok', protocol: 1 })
  assert.equal(runner.diagnostic, null)
})

test('就绪前退出不能报告启动成功', async t => {
  const runner = await fixture(t, async () => ({ binding: { ...binding, model: 'exit' }, assertCurrent() {} }))
  await assert.rejects(runner.start(), /未能取得/)
  assert.equal((await runner.status()).state, 'stopped')
})

test('缺少可执行文件给出受控错误并清理进程句柄', async t => {
  const runner = await fixture(t)
  runner.command = [path.join(tmpdir(), '不存在的-mycollab-runner')]
  await assert.rejects(runner.start(), /无法启动/)
  assert.equal(runner.child, null)
})

test('自检可使用本地配置解析器，不依赖启动用的在线验证', async t => {
  const runner = await fixture(t, async () => { throw Error('offline') })
  runner.resolveLocal = async () => ({ binding, assertCurrent() {} })
  assert.deepEqual(await runner.diagnose(), { opencode: 'ok', server: 'ok', protocol: 1 })
  await assert.rejects(runner.start(), /offline/)
})


test('停止期间仍显示同一设备待发箱摘要，不采用旧运行状态或敏感字段', async t => {
  const runner = await fixture(t)
  const key = createHash('sha256').update(binding.server + '\0' + binding.device_token).digest('hex')
  const directory = path.join(path.dirname(runner.configPath), 'runner-state', key)
  await mkdir(directory, { recursive: true })
  await writeFile(path.join(directory, 'status.json'), JSON.stringify({ state: 'running', pending_results: 3,
    rejected_results: 1, request_id: 'private-request', device_token: binding.device_token }))
  assert.deepEqual(await runner.status(), { state: 'stopped', pending_results: 3, rejected_results: 1, error: '' })
})
