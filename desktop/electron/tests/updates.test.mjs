import { test } from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { UpdateController, updatePolicy, allowedUpdateURL } from '../updates.mjs'
function fixture(prepare = async () => {}) {
  const adapter = new EventEmitter()
  let installed = 0, recovered = 0
  adapter.checkForUpdates = async () => ({ updateInfo: { version: '0.2.0' }, isUpdateAvailable: true })
  adapter.downloadUpdate = async () => { adapter.emit('download-progress', { percent: 150 }); adapter.emit('update-downloaded', {}) }
  adapter.quitAndInstall = () => { installed++ }
  const controller = new UpdateController(adapter, prepare, () => { recovered++ })
  return { controller, adapter, installed: () => installed, recovered: () => recovered }
}

test('更新默认不下载、不随退出安装，只能下载完成并停止 Runner 后安装', async () => {
  let stopped = false
  const { controller, adapter, installed } = fixture(async () => { stopped = true })
  assert.equal(adapter.autoDownload, false)
  assert.equal(adapter.autoInstallOnAppQuit, false)
  assert.equal(adapter.allowDowngrade, false)
  await assert.rejects(controller.install(), /尚未准备好/)
  assert.equal((await controller.check()).state, 'available')
  assert.equal(installed(), 0)
  await controller.download()
  assert.equal(stopped, false)
  assert.equal(controller.snapshot().progress, 100)
  await controller.install()
  assert.equal(stopped, true)
  assert.equal(installed(), 1)
  await assert.rejects(controller.install(), /尚未准备好/)
})

test('Runner 停止失败不调用安装，保留下载供重试', async () => {
  const { controller, installed, recovered } = fixture(async () => { throw Error('stop timeout') })
  await controller.check(); await controller.download()
  await assert.rejects(controller.install(), /客户端保持打开/)
  assert.equal(installed(), 0)
  assert.equal(recovered(), 1)
  assert.equal(controller.snapshot().downloaded, true)
})

test('签名或网络错误脱敏，安装异步失败恢复退出保护', async () => {
  const { controller, adapter, recovered } = fixture()
  adapter.checkForUpdates = async () => { throw Error('https://secret/credential') }
  await assert.rejects(controller.check(), /更新失败/)
  assert.equal(JSON.stringify(controller.snapshot()).includes('credential'), false)
  adapter.checkForUpdates = async () => ({ updateInfo: { version: '0.2.0' }, isUpdateAvailable: true })
  await controller.check(); await controller.download(); await controller.install()
  adapter.emit('error', Error('signature invalid'))
  assert.equal(controller.installing, false)
  assert.equal(recovered(), 1)
})

test('检查期间拒绝重复请求，开发包禁用更新', async () => {
  const { controller, adapter } = fixture()
  let release
  adapter.checkForUpdates = () => new Promise(resolve => { release = resolve })
  const checking = controller.check()
  await assert.rejects(controller.check(), /不能检查/)
  release({ updateInfo: { version: '0.1.0' }, isUpdateAvailable: false })
  assert.equal((await checking).state, 'current')
  const disabled = new UpdateController(null, async () => {}, () => {})
  assert.equal(disabled.snapshot().state, 'disabled')
  await assert.rejects(disabled.check())
})

test('发行更新源绑定平台架构与 HTTPS 目录，拒绝跨源下载和路径绕过', () => {
  const policy = { enabled: true, platform: 'win32', arch: 'x64', publisher: 'Example', url: 'https://updates.example.com/win-x64/' }
  assert.equal(updatePolicy(policy, 'win32', 'x64').url, policy.url)
  for (const change of [{ url: 'http://updates.example.com/' }, { publisher: '' }, { arch: 'arm64' }, { url: 'https://u:p@updates.example.com/' }]) {
    assert.throws(() => updatePolicy({ ...policy, ...change }, 'win32', 'x64'))
  }
  assert.equal(allowedUpdateURL(policy.url + 'latest.yml', policy.url), true)
  for (const url of ['http://updates.example.com/win-x64/a', 'https://evil.test/a', policy.url + '../mac/a', policy.url + '%2fother']) {
    assert.equal(allowedUpdateURL(url, policy.url), false)
  }
})
