/** 桌面协议的受限业务传输；会话对象仅由主进程注入。 */
export const APP_ORIGIN = 'mycollab://app'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
const METHODS = new Set([...SAFE_METHODS, 'POST', 'PUT', 'PATCH', 'DELETE'])
const API_ROOTS = new Set(['auth', 'missions', 'library', 'agent-devices', 'assistance-requests',
  'file-transfers', 'notifications', 'workspace', 'design-elements', 'production-templates',
  'milestones', 'admin', 'members', 'saved-views', 'comments', 'my-work', 'tags'])

export function serverOrigin(value) {
  const url = new URL(value)
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('服务器须为 HTTPS 根地址；仅本机开发服务允许 HTTP。')
  }
  return url.origin
}

export function apiTarget(request, server) {
  const url = new URL(request.url)
  if (url.protocol !== 'mycollab:' || url.host !== 'app' || url.username || url.password ||
      !METHODS.has(request.method) || !/^\/api\/[a-z-]+\//.test(url.pathname) ||
      !API_ROOTS.has(url.pathname.split('/')[2]) || /%2f|%5c|%2e/i.test(url.pathname)) {
    throw new Error('不允许访问此业务地址。')
  }
  if (request.initiatorOrigin && request.initiatorOrigin !== APP_ORIGIN) {
    throw new Error('请求来源不受信任。')
  }
  return serverOrigin(server) + url.pathname + url.search
}

export class BusinessTransport {
  constructor(server, session, { beforeIdentityChange = async () => {} } = {}) {
    this.server = serverOrigin(server)
    this.session = session
    this.beforeIdentityChange = beforeIdentityChange
    this.generation = 0
    this.controllers = new Set()
  }

  async clear() {
    await this.beforeIdentityChange()
    this.generation++
    for (const controller of this.controllers) controller.abort()
    await this.session.clearStorageData()
  }

  async handle(request) {
    const target = apiTarget(request, this.server)
    const identityChange = request.method === 'POST' &&
      ['/api/auth/login/', '/api/auth/logout/'].includes(new URL(target).pathname)
    if (identityChange) {
      await this.beforeIdentityChange()
      this.generation++
      for (const controller of this.controllers) controller.abort()
      if (new URL(target).pathname === '/api/auth/login/') await this.session.clearStorageData()
    }
    const generation = this.generation
    const controller = new AbortController()
    const abort = () => controller.abort()
    request.signal?.addEventListener('abort', abort, { once: true })
    if (request.signal?.aborted) controller.abort()
    this.controllers.add(controller)
    let streaming = false
    const cleanup = () => {
      this.controllers.delete(controller)
      request.signal?.removeEventListener('abort', abort)
    }
    try {
      const headers = new Headers({ Accept: request.headers.get('accept') || '*/*' })
      for (const name of ['content-type', 'range', 'if-none-match', 'if-modified-since']) {
        if (request.headers.has(name)) headers.set(name, request.headers.get(name))
      }
      if (!SAFE_METHODS.has(request.method)) {
        let cookies = await this.session.cookies.get({ url: this.server, name: 'csrftoken' })
        if (!cookies.length) {
          const csrf = await this.session.fetch(this.server + '/api/auth/csrf/', {
            redirect: 'error', signal: controller.signal,
          })
          await csrf.body?.cancel()
          if (!csrf.ok) throw new Error('无法初始化登录保护。')
          cookies = await this.session.cookies.get({ url: this.server, name: 'csrftoken' })
        }
        if (!cookies.length) throw new Error('服务器未提供 CSRF Cookie。')
        headers.set('X-CSRFToken', cookies[0].value)
        headers.set('Origin', this.server)
        headers.set('Referer', this.server + '/')
      }
      const response = await this.session.fetch(target, {
        method: request.method, headers, body: SAFE_METHODS.has(request.method) ? undefined : request.body,
        ...(request.body && !SAFE_METHODS.has(request.method) ? { duplex: 'half' } : {}),
        redirect: 'error', signal: controller.signal,
      })
      if (generation !== this.generation) {
        await response.body?.cancel()
        throw new Error('登录身份已改变，请重新加载。')
      }
      if (identityChange && new URL(target).pathname === '/api/auth/logout/') {
        await this.session.clearStorageData()
      }
      const outgoing = new Headers()
      for (const name of ['content-type', 'content-disposition', 'content-length', 'content-range', 'accept-ranges']) {
        if (response.headers.has(name)) outgoing.set(name, response.headers.get(name))
      }
      outgoing.set('Cache-Control', 'no-store')
      outgoing.set('X-Content-Type-Options', 'nosniff')
      // 私有附件即使是 HTML/SVG，也不能执行脚本或获得宿主能力。
      outgoing.set('Content-Security-Policy', "default-src 'none'; sandbox")
      let body = null
      if (response.body) {
        const reader = response.body.getReader()
        streaming = true
        body = new ReadableStream({
          async pull(stream) {
            try {
              if (controller.signal.aborted) throw new Error('请求已取消。')
              const { done, value } = await reader.read()
              if (controller.signal.aborted) throw new Error('请求已取消。')
              if (done) { stream.close(); cleanup() }
              else stream.enqueue(value)
            } catch (error) { stream.error(error); await reader.cancel().catch(() => {}); cleanup() }
          },
          async cancel(reason) { controller.abort(); await reader.cancel(reason); cleanup() },
        })
      }
      return new Response(body, { status: response.status, headers: outgoing })
    } finally {
      if (!streaming) cleanup()
    }
  }
}
