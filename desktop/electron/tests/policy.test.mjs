import { test } from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { assertSender, assetPath, externalURL, isAppPage, libraryURL } from '../policy.mjs'

test('桌面 IPC 只接受当前主窗口的本地业务主框架', () => {
  const mainFrame = { url: 'mycollab://app/missions/123' }
  const contents = { mainFrame }
  assert.doesNotThrow(() => assertSender({ sender: contents, senderFrame: mainFrame }, contents))
  assert.throws(() => assertSender({ sender: {}, senderFrame: mainFrame }, contents))
  assert.throws(() => assertSender({ sender: contents, senderFrame: { ...mainFrame } }, contents))
  for (const url of ['https://evil.test/', 'mycollab://app/api/library/files/test/', 'mycollab://other/', 'mycollab://app/assets/a.js']) {
    mainFrame.url = url
    assert.throws(() => assertSender({ sender: contents, senderFrame: mainFrame }, contents))
    assert.equal(isAppPage(url), false)
  }
})

test('静态协议只暴露构建资产和路由入口', () => {
  const root = path.resolve('fixture')
  assert.equal(assetPath('mycollab://app/missions/123', root), path.join(root, 'index.html'))
  assert.equal(assetPath('mycollab://app/assets/app.js', root), path.join(root, 'assets/app.js'))
  assert.equal(assetPath('mycollab://app/package.json', root), path.join(root, 'index.html'))
  for (const value of ['mycollab://app/assets/%2e%2e%2fsecret', 'mycollab://app/assets/%5csecret',
    'mycollab://app/api/auth/me/', 'mycollab://elsewhere/assets/a.js', 'file:///secret']) {
    assert.throws(() => assetPath(value, root))
  }
})

test('外链和素材下载拒绝任意协议及路径', () => {
  assert.equal(externalURL('https://example.com/a'), 'https://example.com/a')
  for (const value of ['file:///etc/passwd', 'javascript:alert(1)', 'https://user:pass@example.com', 'cmd:open']) {
    assert.throws(() => externalURL(value))
  }
  const valid = '/api/library/files/11111111-1111-1111-1111-111111111111/'
  assert.equal(libraryURL(valid), 'mycollab://app' + valid)
  for (const value of [valid + '?other=1', 'https://evil.test' + valid, '/api/auth/me/', '/api/library/files/../']) {
    assert.throws(() => libraryURL(value))
  }
})

test('只有用户启用后本地业务页才能申请局域网权限', async () => {
  const { allowPermission } = await import('../policy.mjs')
  assert.equal(allowPermission('local-network', 'mycollab://app/file-transfer', false), false)
  assert.equal(allowPermission('local-network', 'mycollab://app/file-transfer', true), true)
  assert.equal(allowPermission('local-network', 'https://evil.test', true), false)
  assert.equal(allowPermission('media', 'mycollab://app/file-transfer', true), false)
  assert.equal(allowPermission('clipboard-read', 'mycollab://app/', true), false)
  assert.equal(allowPermission('clipboard-sanitized-write', 'mycollab://app/', false), true)
})
