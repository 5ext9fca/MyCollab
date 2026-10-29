import { test } from 'node:test'
import assert from 'node:assert/strict'
import { startServer, payload } from './server.mjs'

test('夹具隔离会话并区分普通 filename 与 UTF-8 filename*', async () => {
  const server = await startServer()
  try {
    assert.equal((await fetch(server.url + '/api/auth/me/')).status, 401)
    const login = await fetch(server.url + '/api/auth/login/', { method: 'POST', body: JSON.stringify({ username: 'acceptance', password: 'fixture-only-password' }) })
    const cookie = login.headers.get('set-cookie').split(';')[0]
    const files = await (await fetch(server.url + '/api/library/files/', { headers: { cookie } })).json()
    for (const [index, file] of files.results.entries()) {
      const response = await fetch(server.url + file.url, { headers: { cookie } })
      assert.equal(response.headers.get('content-disposition').includes('filename*='), index !== 0)
      assert.deepEqual(Buffer.from(await response.arrayBuffer()), payload)
    }
    await fetch(server.url + '/api/auth/logout/', { method: 'POST', headers: { cookie } })
    assert.equal((await fetch(server.url + '/api/auth/me/', { headers: { cookie } })).status, 401)
    assert.deepEqual(server.unexpected, [])
  } finally { await server.close() }
})
