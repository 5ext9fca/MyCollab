// 仅供宿主回归的本机 HTTP 夹具，不实现或替代 Django 业务规则。
import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

export const payload = Buffer.from('Windows 素材验收\n同一内容用于英文、中文和日文文件名。\n')
export const names = ['acceptance.txt', '验收 中文文件.txt', 'テスト.txt']
const user = { id: 1, username: 'acceptance', display_name: '自动验收', is_staff: false }
const paginated = results => ({ count: results.length, next: null, previous: null, results })

export async function startServer() {
  const sessions = new Set()
  const unexpected = []
  const files = names.map((name, index) => ({ id: `00000000-0000-4000-8000-00000000000${index}`,
    original_name: name, content_type: 'text/plain', size: payload.length,
    url: `/api/library/files/00000000-0000-4000-8000-00000000000${index}/`, created_at: '2026-10-29T00:00:00Z' }))
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1')
    const send = (status, data, headers = {}) => {
      res.writeHead(status, { 'Content-Type': 'application/json', ...headers })
      res.end(status === 204 ? undefined : JSON.stringify(data))
    }
    try {
      if (url.pathname === '/api/auth/csrf/') return send(200, {}, { 'Set-Cookie': 'csrftoken=fixture-csrf; Path=/; SameSite=Lax' })
      if (url.pathname === '/api/auth/login/' && req.method === 'POST') {
        const chunks = []
        for await (const chunk of req) chunks.push(chunk)
        const input = JSON.parse(Buffer.concat(chunks).toString())
        if (input.username !== 'acceptance' || input.password !== 'fixture-only-password') return send(400, { code: 'invalid_credentials', message: '测试账号不匹配', field_errors: {} })
        const token = randomUUID(); sessions.add(token)
        return send(200, user, { 'Set-Cookie': `sessionid=${token}; Path=/; HttpOnly; SameSite=Lax` })
      }
      const token = /(?:^|;\s*)sessionid=([^;]+)/.exec(req.headers.cookie || '')?.[1]
      if (!sessions.has(token)) return send(401, { code: 'not_authenticated', message: '请登录', field_errors: {} })
      if (url.pathname === '/api/auth/logout/' && req.method === 'POST') { sessions.delete(token); return send(204) }
      if (req.method !== 'GET') { unexpected.push(`${req.method} ${url.pathname}`); return send(405, {}) }
      if (url.pathname === '/api/auth/me/') return send(200, user)
      if (url.pathname === '/api/notifications/summary/') return send(200, { unread_count: 0 })
      if (url.pathname === '/api/my-work/summary/') return send(200, { today: '2026-10-29', unread_notification_count: 0,
        counts: { review: 0, returned: 0, due_soon: 0, overdue: 0, unblocked: 0, revalidation: 0 } })
      if (url.pathname === '/api/tags/') return send(200, [])
      if (['/api/my-work/missions/', '/api/notifications/', '/api/missions/', '/api/milestones/'].includes(url.pathname)) return send(200, paginated([]))
      if (url.pathname === '/api/library/files/') return send(200, paginated(files))
      const file = files.find(item => item.url === url.pathname)
      if (file) {
        const disposition = /^[\x20-\x7e]+$/.test(file.original_name)
          ? `attachment; filename="${file.original_name}"`
          : `attachment; filename*=UTF-8''${encodeURIComponent(file.original_name)}`
        res.writeHead(200, { 'Content-Type': 'text/plain', 'Content-Disposition': disposition })
        return res.end(payload)
      }
      if (url.pathname === '/api/design-elements/') {
        const parent = url.searchParams.get('parent')
        const results = url.searchParams.get('kind') === 'Asset' ? [] : parent === 'root'
          ? [{ id: 'parent', title: '验收父设计', kind: 'Design', has_children: true, archived: false }]
          : parent === 'parent' ? [{ id: 'child', title: '验收子设计', kind: 'Design', has_children: false, archived: false }] : []
        return send(200, paginated(results))
      }
      unexpected.push(`${req.method} ${url.pathname}`)
      send(404, { code: 'fixture_missing', message: '测试夹具未覆盖此接口', field_errors: {} })
    } catch { send(500, { code: 'fixture_error', message: '测试夹具处理失败', field_errors: {} }) }
  })
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  return { url: `http://127.0.0.1:${server.address().port}`, unexpected,
    close: () => new Promise(resolve => { server.close(resolve); server.closeAllConnections() }) }
}
