import path from 'node:path'
import { APP_ORIGIN } from './transport.mjs'

export const CONTENT_SECURITY_POLICY = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: http: data: blob:; font-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"

/** @param {string} value */
export function isAppPage(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'mycollab:' && url.host === 'app' && !url.username && !url.password &&
      !url.pathname.startsWith('/api/') && !url.pathname.startsWith('/assets/') && !path.posix.extname(url.pathname)
  } catch { return false }
}

/** @param {import('electron').IpcMainInvokeEvent} event @param {import('electron').WebContents | undefined} contents */
export function assertSender(event, contents) {
  if (!contents || event.sender !== contents || !event.senderFrame || event.senderFrame !== contents.mainFrame ||
      !isAppPage(event.senderFrame.url)) throw new Error('不允许此页面调用桌面功能。')
}

/** @param {unknown} value */
export function externalURL(value) {
  if (typeof value !== 'string' || value.length > 8192) throw new Error('外链地址无效。')
  const url = new URL(value)
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('仅允许 HTTP(S) 外链。')
  return url.href
}

/** @param {unknown} value */
export function libraryURL(value) {
  if (typeof value !== 'string') throw new Error('素材地址无效。')
  const url = new URL(value, APP_ORIGIN)
  if (url.protocol !== 'mycollab:' || url.host !== 'app' || url.username || url.password ||
      !/^\/api\/library\/files\/[0-9a-f-]{36}\/$/i.test(url.pathname) || url.search || url.hash) {
    throw new Error('仅允许下载当前用户的素材。')
  }
  return url.href
}

/** @param {string} value @param {string} root */
export function assetPath(value, root) {
  const url = new URL(value)
  if (url.protocol !== 'mycollab:' || url.host !== 'app' || url.username || url.password) throw new Error('页面来源无效。')
  const pathname = decodeURIComponent(url.pathname)
  if (pathname.includes('\\') || pathname.includes('\0') || pathname.split('/').includes('..') || pathname.startsWith('/api/')) {
    throw new Error('资源路径无效。')
  }
  // 仅暴露构建资产和 SPA 入口，不把整个应用目录作为文件服务器。
  const relative = pathname.startsWith('/assets/') ? pathname.slice(1) : ['/favicon.svg', '/theme-init.js'].includes(pathname) ? pathname.slice(1) : 'index.html'
  const result = path.resolve(root, relative)
  if (!result.startsWith(path.resolve(root) + path.sep)) throw new Error('资源路径越界。')
  return result
}

/** @param {string} permission @param {string} requestingURL @param {boolean} localNetwork */
export function allowPermission(permission, requestingURL, localNetwork) {
  if (!isAppPage(requestingURL)) return false
  if (permission === 'clipboard-sanitized-write') return true
  return localNetwork === true && ['local-network', 'local-network-access', 'loopback-network'].includes(permission)
}
