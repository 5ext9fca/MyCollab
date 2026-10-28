import { test } from 'node:test'
import assert from 'node:assert/strict'
import { BusinessTransport, apiTarget, serverOrigin } from '../transport.mjs'
const request = (path, options) => new Request('mycollab://app' + path, options)

 test('服务器与业务路径不允许外部代理、Runner 身份或编码绕过', () => {
  assert.equal(serverOrigin('https://example.com/'), 'https://example.com')
  assert.equal(serverOrigin('http://127.0.0.1:8000'), 'http://127.0.0.1:8000')
  for (const value of ['http://example.com', 'https://a:b@example.com', 'https://example.com/path', 'file:///tmp']) {
    assert.throws(() => serverOrigin(value))
  }
  for (const url of ['https://evil.test/api/missions/', 'mycollab://other/api/missions/',
    'mycollab://app/api/agent-runner/claim/', 'mycollab://app/api/missions/%2fsecret']) {
    assert.throws(() => apiTarget(new Request(url), 'https://example.com'))
  }
  assert.throws(() => apiTarget({ ...{ url: 'mycollab://app/api/missions/', method: 'GET' },
    initiatorOrigin: 'https://evil.test' }, 'https://example.com'))
})

function fixture() {
  const calls = []
  let cleared = 0
  const session = {
    cookies: { get: async () => [{ value: 'csrf-secret' }] },
    clearStorageData: async () => { cleared++ },
    fetch: async (url, options) => {
      calls.push({ url, options, cleared })
      return new Response('{"ok":true}', { headers: { 'Set-Cookie': 'sessionid=secret',
        'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } })
    },
  }
  return { calls, session, transport: new BusinessTransport('https://example.com', session) }
}

test('写入只透传必要头，CSRF 在主进程轮换，响应不泄漏 Cookie', async () => {
  const { transport, calls } = fixture()
  const response = await transport.handle(request('/api/missions/', { method: 'POST', body: '{}',
    headers: { Authorization: 'Bearer evil', Cookie: 'evil', 'X-CSRFToken': 'evil', 'Content-Type': 'application/json' } }))
  assert.equal(await response.text(), '{"ok":true}')
  const { headers, redirect } = calls[0].options
  assert.equal(headers.get('Authorization'), null)
  assert.equal(headers.get('Cookie'), null)
  assert.equal(headers.get('X-CSRFToken'), 'csrf-secret')
  assert.equal(headers.get('Origin'), 'https://example.com')
  assert.equal(redirect, 'error')
  assert.equal(response.headers.get('set-cookie'), null)
  assert.equal(response.headers.get('access-control-allow-origin'), null)
  assert.equal(response.headers.get('cache-control'), 'no-store')
})

test('登录先清旧身份，退出先调用服务端再清会话', async () => {
  for (const action of ['login', 'logout']) {
    const { transport, calls } = fixture()
    const response = await transport.handle(request(`/api/auth/${action}/`, { method: 'POST', body: '{}' }))
    await response.text()
    assert.equal(calls[0].cleared, action === 'login' ? 1 : 0)
  }
})

test('切换身份中断尚未读完的私有文件', async () => {
  const { transport } = fixture()
  const response = await transport.handle(request('/api/library/files/abc/'))
  await transport.clear()
  await assert.rejects(response.text())
})

test('服务器重定向失败不被包装为成功', async () => {
  const { transport, session } = fixture()
  session.fetch = async () => { throw new TypeError('redirect rejected') }
  await assert.rejects(transport.handle(request('/api/missions/')), /redirect rejected/)
  assert.equal(transport.controllers.size, 0)
})

test('网络失败时退出仍清除业务 Cookie', async () => {
  const { transport, session } = fixture()
  let cleared = false
  session.clearStorageData = async () => { cleared = true }
  session.fetch = async () => { throw new Error('offline') }
  await assert.rejects(transport.handle(request('/api/auth/logout/', { method: 'POST' })), /offline/)
  assert.equal(cleared, true)
  assert.equal(transport.changingIdentity, false)
})

test('身份切换期间拒绝并发登录与旧页面请求', async () => {
  const { transport } = fixture()
  let release
  transport.beforeIdentityChange = () => new Promise(resolve => { release = resolve })
  const login = transport.handle(request('/api/auth/login/', { method: 'POST', body: '{}' }))
  await assert.rejects(transport.handle(request('/api/missions/')), /正在切换/)
  await assert.rejects(transport.handle(request('/api/auth/login/', { method: 'POST' })), /正在切换/)
  release()
  await (await login).text()
  assert.equal(transport.changingIdentity, false)
})

test('停止 Runner 失败时保留业务会话并拒绝登录退出', async () => {
  for (const action of ['login', 'logout']) {
    const { transport, session, calls } = fixture()
    let cleared = false
    session.clearStorageData = async () => { cleared = true }
    transport.beforeIdentityChange = async () => { throw new Error('Runner 尚未停止') }
    await assert.rejects(transport.handle(request(`/api/auth/${action}/`, { method: 'POST' })), /尚未停止/)
    assert.equal(cleared, false)
    assert.equal(calls.length, 0)
    assert.equal(transport.changingIdentity, false)
  }
})
