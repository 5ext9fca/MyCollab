// 显式运行的安装副本性能测量；仅使用临时配置及本机 HTTP 夹具。
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { mkdir, mkdtemp, rm, stat, writeFile } from 'node:fs/promises'
import { tmpdir, release, cpus, totalmem } from 'node:os'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { setTimeout as delay } from 'node:timers/promises'
import { startServer } from '../tests/shared/server.mjs'

const { values } = parseArgs({ options: { app: { type: 'string' }, installer: { type: 'string' },
  output: { type: 'string' }, runs: { type: 'string', default: '3' } } })
if (!values.app || !values.installer || !values.output || !['darwin', 'win32'].includes(process.platform)) {
  throw new Error('在 macOS/Windows 运行，必须指定 --app 可执行文件 --installer 安装包 --output JSON 路径。')
}
const runs = Number(values.runs)
if (!Number.isInteger(runs) || runs < 1 || runs > 10) throw new Error('--runs 必须为 1 至 10。')
const executablePath = path.resolve(values.app)
const appAsar = path.resolve(path.dirname(executablePath), process.platform === 'darwin' ? '../Resources/app.asar' : 'resources/app.asar')
const installer = path.resolve(values.installer)
const output = path.resolve(values.output)
await stat(executablePath)
const installerBytes = (await stat(installer)).size
const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { _electron, expect } = require('@playwright/test')
const digest = async filename => {
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(filename)) hash.update(chunk)
  return hash.digest('hex')
}
const report = { schema: 1, createdAt: new Date().toISOString(), platform: process.platform,
  arch: process.arch, os: release(), cpu: cpus()[0]?.model, logicalCpus: cpus().length,
  systemMemoryBytes: totalmem(), installerBytes, installerSha256: await digest(installer),
  executableSha256: await digest(executablePath), appAsarSha256: await digest(appAsar), samples: [], complete: false,
  scope: '实际安装副本、全新临时配置、本机 HTTP 夹具；不清空 OS 缓存。含自动化通信耗时；非真实服务器、传输峰值、Runner 运行或最低配置验收。',
  memorySemantics: 'app.getAppMetrics 的 workingSetSize（KB）按进程求和；共享页可能重复计算，不等于系统独占内存。',
}
try {
  for (let index = 0; index < runs; index++) {
    const server = await startServer()
    const profile = await mkdtemp(path.join(tmpdir(), 'mycollab-performance-'))
    let app
    try {
      const env = { ...process.env }
      delete env.ELECTRON_RUN_AS_NODE
      const started = performance.now()
      app = await _electron.launch({ executablePath, args: [`--user-data-dir=${profile}`], env, timeout: 30000 })
      const page = await app.firstWindow()
      await expect(page.getByPlaceholder('https://collab.example.com')).toBeVisible()
      const startupMs = Math.round(performance.now() - started)
      const identity = await app.evaluate(({ app }) => ({ packaged: app.isPackaged,
        profile: app.getPath('userData'), electron: process.versions.electron, chrome: process.versions.chrome }))
      expect(identity.packaged).toBe(true)
      expect(identity.profile).toBe(profile)
      await page.getByPlaceholder('https://collab.example.com').fill(server.url)
      await page.getByRole('button', { name: '保存服务器并前往登录' }).click()
      await expect(page).toHaveURL(/\/login$/)
      await page.getByRole('textbox', { name: '用户名' }).fill('acceptance')
      await page.locator('input[type=password]').fill('fixture-only-password')
      const loginStarted = performance.now()
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await expect(page).toHaveURL(/\/my-work$/)
      await expect(page.getByRole('menuitem', { name: '素材库', exact: true })).toBeVisible()
      const loginMs = Math.round(performance.now() - loginStarted)
      const libraryStarted = performance.now()
      await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
      await expect(page.getByRole('link', { name: 'acceptance.txt', exact: true })).toBeVisible()
      const libraryMs = Math.round(performance.now() - libraryStarted)
      // 明确的空闲采样窗口，不将页面初次渲染峰值称为空闲内存。
      await delay(10000)
      const memorySamples = []
      for (let sample = 0; sample < 5; sample++) {
        memorySamples.push(await app.evaluate(({ app }) => app.getAppMetrics().map(item => ({
          type: item.type, workingSetKB: item.memory.workingSetSize,
        }))))
        if (sample < 4) await delay(1000)
      }
      expect(server.unexpected).toEqual([])
      report.samples.push({ index: index + 1, electron: identity.electron, chrome: identity.chrome,
        startupMs, loginMs, libraryMs, memorySamples,
        workingSetTotalsKB: memorySamples.map(items => items.reduce((sum, item) => sum + item.workingSetKB, 0)) })
      console.log(`第 ${index + 1}/${runs} 轮完成：启动 ${startupMs} ms，登录 ${loginMs} ms，素材库 ${libraryMs} ms`)
    } finally {
      try { if (app) await app.close() }
      finally { await server.close(); await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 }) }
    }
  }
  report.complete = true
} finally {
  await mkdir(path.dirname(output), { recursive: true })
  await writeFile(output, JSON.stringify(report, null, 2) + '\n')
  console.log(`性能测量记录：${output}`)
}
