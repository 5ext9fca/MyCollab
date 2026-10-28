/** 更新只由用户逐步触发；此控制器不接受页面提供的地址或安装路径。 */
export class UpdateController {
  /** @param {import('electron-updater').AppUpdater | null} updater
   * @param {() => Promise<void>} prepareInstall @param {() => void} recoverInstall */
  constructor(updater, prepareInstall, recoverInstall) {
    this.updater = updater; this.prepareInstall = prepareInstall; this.recoverInstall = recoverInstall
    this.state = updater ? 'idle' : 'disabled'
    this.version = ''; this.progress = 0; this.error = ''; this.busy = false; this.installing = false
    this.available = false; this.downloaded = false
    if (!updater) return
    updater.autoDownload = false
    updater.autoInstallOnAppQuit = false
    updater.allowDowngrade = false
    updater.allowPrerelease = false
    updater.logger = null
    updater.on('error', () => this.fail())
    updater.on('download-progress', value => {
      if (this.state === 'downloading' && Number.isFinite(value.percent)) this.progress = Math.max(0, Math.min(100, Math.floor(value.percent)))
    })
    updater.on('update-downloaded', () => { this.downloaded = true; this.state = 'ready'; this.progress = 100 })
  }

  snapshot() { return { state: this.state, version: this.version, progress: this.progress, error: this.error,
    available: this.available, downloaded: this.downloaded } }

  fail() {
    if (this.installing) this.recoverInstall()
    this.installing = false
    this.state = 'error'
    this.error = '更新失败，请检查网络、发行签名或稍后重试；当前版本仍可使用。'
  }

  async check() {
    if (!this.updater || this.busy || this.installing || this.downloaded) throw new Error('当前不能检查更新。')
    this.busy = true; this.state = 'checking'; this.error = ''; this.available = false; this.version = ''
    try {
      const result = await this.updater.checkForUpdates()
      if (!result) throw new Error('更新服务不可用。')
      const version = result.updateInfo.version
      if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version) || version.length > 100) throw new Error('更新版本格式无效。')
      this.version = version
      this.available = result.isUpdateAvailable === true
      this.state = this.available ? 'available' : 'current'
      return this.snapshot()
    } catch { this.fail(); throw new Error(this.error) }
    finally { this.busy = false }
  }

  async download() {
    if (!this.updater || this.busy || this.installing || !this.available || this.downloaded) throw new Error('请先检查可用更新。')
    this.busy = true; this.state = 'downloading'; this.error = ''; this.progress = 0
    try {
      await this.updater.downloadUpdate()
      if (!this.downloaded) throw new Error('更新尚未下载完成。')
      return this.snapshot()
    } catch { this.fail(); throw new Error(this.error) }
    finally { this.busy = false }
  }

  async install() {
    if (!this.updater || this.busy || this.installing || !this.downloaded) throw new Error('更新尚未准备好。')
    this.installing = true; this.state = 'installing'; this.error = ''
    try {
      await this.prepareInstall()
      if (!this.installing) throw new Error('安装准备已失败。')
      this.updater.quitAndInstall(false, true)
      return this.snapshot()
    } catch { this.fail(); throw new Error('未能停止 Runner 或安装更新，客户端保持打开。') }
  }
}

/** @param {unknown} input @param {string} platform @param {string} arch */
export function updatePolicy(input, platform, arch) {
  if (!input || typeof input !== 'object') return null
  const value = /** @type {Record<string, unknown>} */ (input)
  if (value.enabled !== true) return null
  if (value.platform !== platform || value.arch !== arch || typeof value.url !== 'string') throw new Error('发行平台配置无效。')
  const url = new URL(value.url)
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || !url.pathname.endsWith('/')) throw new Error('更新源必须是固定 HTTPS 目录。')
  if (platform === 'win32' && (typeof value.publisher !== 'string' || !value.publisher.trim())) throw new Error('Windows 更新缺少签名发布者。')
  return { url: url.href }
}

/** 更新清单、包和重定向都只能访问发行时固定的平台/架构目录。
 * @param {string} request @param {string} base */
export function allowedUpdateURL(request, base) {
  try {
    const target = new URL(request), root = new URL(base)
    return target.protocol === 'https:' && target.origin === root.origin && !target.username && !target.password &&
      target.pathname.startsWith(root.pathname) && !/%(?:2f|5c|2e)/i.test(target.pathname)
  } catch { return false }
}
