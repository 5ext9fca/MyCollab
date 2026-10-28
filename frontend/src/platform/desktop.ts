export interface DesktopSettings {
  server: string
  localNetwork: boolean
  autostart: boolean
  version: string
  electron: string
  chromium: string
  platform: string
  arch: string
}
export interface DesktopBridge {
  settings(): Promise<DesktopSettings>
  setServer(server: string): Promise<boolean>
  setLocalNetwork(enabled: boolean): Promise<boolean>
  setAutostart(enabled: boolean): Promise<boolean>
  openExternal(url: string): Promise<void>
  downloadLibrary(url: string): Promise<boolean>
}
declare global {
  interface Window { mycollabDesktop?: DesktopBridge }
}
export const desktop = window.mycollabDesktop

/** 链接仍按原有 Markdown 清洗规则生成，桌面只改变打开方式。 */
export function installDesktopLinks(onError: (message: string) => void): void {
  if (!desktop) return
  const bridge = desktop
  document.addEventListener('click', event => {
    const link = event.target instanceof Element ? event.target.closest('a') : null
    if (!link || link.hasAttribute('download')) return
    const url = new URL(link.href, location.href)
    let operation: Promise<unknown> | undefined
    if (url.protocol === 'mycollab:' && url.host === 'app' && url.pathname.startsWith('/api/library/files/')) {
      operation = bridge.downloadLibrary(url.href)
    } else if (url.protocol === 'https:' || url.protocol === 'http:') {
      operation = bridge.openExternal(url.href)
    } else return
    event.preventDefault()
    event.stopPropagation()
    void operation.catch(() => onError('无法打开链接或保存文件，请检查网络、权限和登录状态。'))
  }, true)
}
