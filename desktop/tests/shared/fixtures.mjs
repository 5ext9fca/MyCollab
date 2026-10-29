import { test as base, expect, _electron } from '@playwright/test'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { startServer } from './server.mjs'

export { expect }
export const test = base.extend({
  desktop: async ({}, use, testInfo) => {
    await mkdir(testInfo.outputDir, { recursive: true })
    const server = await startServer()
    const profile = await mkdtemp(path.join(tmpdir(), 'mycollab-playwright-'))
    let app
    let page
    const launch = async () => {
      app = await _electron.launch({ executablePath: process.env.MYCOLLAB_TEST_APP_BINARY,
        args: [`--user-data-dir=${profile}`], timeout: 20000 })
      await app.context().tracing.start({ screenshots: true, snapshots: true })
      page = await app.firstWindow()
      expect(await app.evaluate(({ app }) => app.getPath('userData'))).toBe(profile)
      expect(await app.evaluate(({ app }) => app.isPackaged)).toBe(true)
      expect(await app.evaluate(() => process.platform)).toBe(process.env.MYCOLLAB_TEST_PLATFORM)
    }
    const stop = async label => {
      if (!app) return
      const current = app
      app = undefined
      try { await current.context().tracing.stop({ path: testInfo.outputPath(`${label}.zip`) }) }
      finally { await current.close() }
    }
    try {
      await launch()
      await expect(page.getByPlaceholder('https://collab.example.com')).toBeVisible()
      await page.getByPlaceholder('https://collab.example.com').fill(server.url)
      await page.getByRole('button', { name: '保存服务器并前往登录' }).click()
      await expect(page).toHaveURL(/\/login$/)
      await page.getByRole('textbox', { name: '用户名' }).fill('acceptance')
      await page.locator('input[type=password]').fill('fixture-only-password')
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await expect(page).toHaveURL(/\/my-work$/)
      await use({ get app() { return app }, get page() { return page }, profile,
        restart: async () => { await stop('before-restart'); await launch() } })
    } finally {
      try {
        if (app && page && !page.isClosed()) {
          await page.screenshot({ path: testInfo.outputPath('final.png'), fullPage: true }).catch(() => {})
        }
        await stop('trace')
      } finally {
        await server.close()
        await writeFile(testInfo.outputPath('fixture-requests.json'), JSON.stringify(server.unexpected, null, 2))
        // 仅删除本测试创建的临时配置；不触碰日常客户端配置。
        await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 })
      }
      expect(server.unexpected, '出现夹具未覆盖的接口，不能误判为产品通过').toEqual([])
    }
  },
})
