import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, net, protocol, safeStorage, session, shell, Tray } from 'electron'
import { createHash, randomUUID } from 'node:crypto'
import { createWriteStream } from 'node:fs'
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { RunnerController } from './runner.mjs'
import { BindingVault } from './vault.mjs'
import { DeviceBindings } from './binding.mjs'
import { APP_ORIGIN, BusinessTransport, serverOrigin } from './transport.mjs'
import { allowPermission, assertSender, assetPath, CONTENT_SECURITY_POLICY, externalURL, isAppPage, libraryURL } from './policy.mjs'

const directory = path.dirname(fileURLToPath(import.meta.url))
protocol.registerSchemesAsPrivileged([{ scheme: 'mycollab', privileges: {
  standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true,
} }])
app.setName('MyCollab')
/** @type {BrowserWindow} */
let window
/** @type {Tray} */
let tray
/** @type {BusinessTransport | undefined} */
let transport
/** @type {import('electron').Session} */
let rendererSession
/** @type {DeviceBindings} */
let bindings
/** @type {RunnerController | undefined} */
let runner
let bindingRunner = false
let finishingQuit = false
let quitting = false
let changingServer = false
let settings = { server: '', localNetwork: false }
const frontend = app.isPackaged ? path.join(process.resourcesPath, 'frontend') : path.resolve(directory, '../../frontend/dist')
const configPath = () => path.join(app.getPath('userData'), 'desktop.json')
/** @param {number} status @param {string} code @param {string} message */
const errorResponse = (status, code, message) => Response.json({ code, message, field_errors: {} }, { status })

/** @param {{server: string, localNetwork: boolean}} value */
async function saveSettings(value) {
  const destination = configPath()
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 })
  const temporary = destination + '.' + randomUUID()
  try {
    await writeFile(temporary, JSON.stringify(value), { mode: 0o600, flag: 'wx' })
    await rename(temporary, destination)
  } finally { await rm(temporary, { force: true }) }
}

/** @param {string} server */
function configureServer(server) {
  if (!server) { transport = undefined; return }
  const key = createHash('sha256').update(server).digest('hex')
  // 业务会话与渲染页面彻底分离；退出应用后不保留登录 Cookie。
  const businessSession = session.fromPartition('business-' + key, { cache: false })
  transport = new BusinessTransport(server, businessSession, { beforeIdentityChange: async () => { await runner?.stop() } })
}

/** @param {Request & {initiatorOrigin?: string}} request */
async function serve(request) {
  try {
    const url = new URL(request.url)
    if (url.pathname.startsWith('/api/')) {
      if (changingServer) return errorResponse(409, 'identity_changing', '服务器正在切换。')
      if (!transport) return errorResponse(503, 'server_required', '请先设置协作服务器。')
      return await transport.handle(request)
    }
    if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, { status: 405 })
    const filename = assetPath(request.url, frontend)
    const response = await net.fetch(pathToFileURL(filename).href)
    const headers = new Headers(response.headers)
    headers.set('Content-Security-Policy', CONTENT_SECURITY_POLICY)
    headers.set('X-Content-Type-Options', 'nosniff')
    headers.set('Cache-Control', 'no-store')
    return new Response(request.method === 'HEAD' ? null : response.body, { status: response.status, headers })
  } catch {
    return errorResponse(502, 'desktop_connection_failed', '连接失败，请检查服务器地址、网络或证书后重试。')
  }
}

/** @param {unknown} value */
async function downloadLibrary(value) {
  const url = libraryURL(value)
  const current = transport
  if (!current || changingServer) throw new Error('请先连接服务器。')
  const generation = current.generation
  const response = await current.handle(new Request(url))
  if (!response.ok || !response.body) { await response.body?.cancel(); throw new Error('素材下载失败或无权访问。') }
  const filename = /filename\*=UTF-8''([^;]+)/i.exec(response.headers.get('content-disposition') || '')?.[1]
  let defaultPath = '素材文件'
  try { if (filename) defaultPath = path.basename(decodeURIComponent(filename)).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_') } catch { /* 使用安全默认名称。 */ }
  const choice = await dialog.showSaveDialog(window, { defaultPath })
  if (choice.canceled || !choice.filePath) { await response.body.cancel(); return false }
  if (current !== transport || current.generation !== generation) { await response.body.cancel(); throw new Error('登录身份已改变。') }
  const temporary = choice.filePath + '.mycollab-' + randomUUID() + '.partial'
  try {
    const reader = response.body.getReader()
    const chunks = async function* () {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) return
          yield value
        }
      } finally { await reader.cancel().catch(() => {}) }
    }
    await pipeline(Readable.from(chunks()), createWriteStream(temporary, { mode: 0o600, flags: 'wx' }))
    if (current !== transport || current.generation !== generation) throw new Error('登录身份已改变。')
    await rename(temporary, choice.filePath)
    return true
  } finally { await rm(temporary, { force: true }) }
}

/** @param {string} channel @param {(...args: unknown[]) => unknown} operation */
function handle(channel, operation) {
  ipcMain.handle(channel, async (event, ...args) => {
    assertSender(event, window?.webContents)
    return operation(...args)
  })
}

function registerIPC() {
  handle('desktop:runner-binding', () => bindings.read())
  handle('desktop:bind-runner', async input => {
    if (bindingRunner || finishingQuit || changingServer) throw new Error('本机配置正在切换，请稍后重试。')
    bindingRunner = true
    try { await runner?.stop(); return await bindings.bind(input) }
    finally { bindingRunner = false }
  })
  handle('desktop:runner-start', () => {
    if (bindingRunner || finishingQuit || changingServer) throw new Error('本机配置正在切换，请稍后重试。')
    return runner?.start()
  })
  handle('desktop:runner-stop', () => runner?.stop())
  handle('desktop:runner-status', () => runner?.status())
  handle('desktop:runner-diagnose', () => {
    if (bindingRunner || finishingQuit || changingServer) throw new Error('本机配置正在切换，请稍后重试。')
    return runner?.diagnose()
  })
  handle('desktop:settings', () => ({ server: settings.server, localNetwork: settings.localNetwork,
    autostart: app.getLoginItemSettings().openAtLogin, version: app.getVersion(),
    electron: process.versions.electron, chromium: process.versions.chrome,
    platform: process.platform, arch: process.arch }))
  handle('desktop:set-server', async (value) => {
    if (changingServer) throw new Error('服务器正在切换。')
    if (typeof value !== 'string' || value.length > 2048) throw new Error('服务器地址无效。')
    const server = serverOrigin(value.trim())
    changingServer = true
    try {
      await transport?.clear()
      await rendererSession.clearStorageData()
      await saveSettings({ ...settings, server })
      settings = { ...settings, server }
      configureServer(server)
      // 重建整个页面，取消旧身份的轮询、对象 URL 与组件状态。
      await window.loadURL(APP_ORIGIN + '/login')
      return true
    } finally { changingServer = false }
  })
  handle('desktop:set-local-network', async (enabled) => {
    if (typeof enabled !== 'boolean' || changingServer) throw new Error('局域网权限设置无效。')
    await saveSettings({ ...settings, localNetwork: enabled })
    settings = { ...settings, localNetwork: enabled }
    return enabled
  })
  handle('desktop:set-autostart', (enabled) => {
    if (typeof enabled !== 'boolean') throw new Error('自启动设置无效。')
    app.setLoginItemSettings({ openAtLogin: enabled })
    return app.getLoginItemSettings().openAtLogin
  })
  handle('desktop:external', (url) => shell.openExternal(externalURL(url)))
  handle('desktop:download-library', downloadLibrary)
}

function reveal() { if (window) { window.show(); window.focus() } }

function createWindow() {
  window = new BrowserWindow({ width: 1280, height: 840, minWidth: 720, minHeight: 520,
    title: 'MyCollab', webPreferences: { preload: path.join(directory, 'preload.cjs'),
      session: rendererSession, nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, webviewTag: false, spellcheck: false } })
  window.webContents.on('will-navigate', (event, url) => {
    if (!isAppPage(url)) {
      event.preventDefault()
      if (url.startsWith(APP_ORIGIN + '/api/library/files/')) void downloadLibrary(url).catch(() => {})
      else { try { void shell.openExternal(externalURL(url)).catch(() => {}) } catch { /* 拒绝其他协议。 */ } }
    }
  })
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(APP_ORIGIN + '/api/library/files/')) void downloadLibrary(url).catch(() => {})
    else { try { void shell.openExternal(externalURL(url)).catch(() => {}) } catch { /* 不创建外部页面。 */ } }
    return { action: 'deny' }
  })
  window.webContents.on('will-attach-webview', event => event.preventDefault())
  window.on('close', event => { if (!quitting) { event.preventDefault(); window.hide() } })
  void window.loadURL(APP_ORIGIN + (settings.server ? '/' : '/desktop-settings'))
}

if (!app.requestSingleInstanceLock()) app.quit()
else {
  app.on('second-instance', reveal)
  app.on('activate', reveal)
  app.on('before-quit', event => {
    if (quitting) return
    event.preventDefault()
    if (finishingQuit) return
    finishingQuit = true
    void (runner?.stop() || Promise.resolve()).then(() => { quitting = true; app.quit() }).catch(() => {
      finishingQuit = false
      reveal()
      dialog.showErrorBox('Runner 尚未停止', '客户端保持打开，请稍后再次停止 Runner，再退出。')
    })
  })
  await app.whenReady()
  try {
    const stored = JSON.parse(await readFile(configPath(), 'utf8'))
    settings = { server: stored.server ? serverOrigin(stored.server) : '', localNetwork: stored.localNetwork === true }
  } catch { settings = { server: '', localNetwork: false } }
  configureServer(settings.server)
  rendererSession = session.fromPartition('renderer', { cache: false })
  rendererSession.setPermissionRequestHandler((contents, permission, callback, details) => {
    callback(contents === window?.webContents && details.isMainFrame === true &&
      allowPermission(permission, details.requestingUrl, settings.localNetwork))
  })
  rendererSession.setPermissionCheckHandler((contents, permission, origin, details) =>
    contents !== null && contents === window?.webContents && origin === APP_ORIGIN && details.isMainFrame === true &&
    allowPermission(permission, contents.getURL(), settings.localNetwork))
  rendererSession.protocol.handle('mycollab', serve)
  const vault = new BindingVault(path.join(app.getPath('userData'), 'devices'), safeStorage)
  const deviceSession = session.fromPartition('device-probe', { cache: false })
  bindings = new DeviceBindings(() => changingServer ? undefined : transport, vault,
    (input, options) => deviceSession.fetch(input instanceof URL ? input.href : input, options))
  const platform = process.platform === 'darwin' ? 'mac' : 'win'
  const runnerDirectory = app.isPackaged ? path.join(process.resourcesPath, 'runner') : path.join(directory, '../build/runner', `${platform}-${process.arch}`)
  runner = new RunnerController([path.join(runnerDirectory, process.platform === 'win32' ? 'mycollab-runner.exe' : 'mycollab-runner')],
    path.join(app.getPath('userData'), 'runner', 'config.json'), () => bindings.verified())
  registerIPC()
  createWindow()
  const icon = nativeImage.createFromPath(path.join(directory, '../src-tauri/icons/icon.png')).resize({ width: 18, height: 18 })
  tray = new Tray(icon)
  tray.setToolTip('MyCollab')
  tray.setContextMenu(Menu.buildFromTemplate([{ label: '显示 MyCollab', click: reveal },
    { label: '退出', click: () => app.quit() }]))
  tray.on('click', reveal)
}
