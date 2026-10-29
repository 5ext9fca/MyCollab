import { test, expect, _electron as electron } from '@playwright/test'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
test('真实宿主设置服务器、登录、导航、刷新与退出', async ({}, testInfo) => {
  const server = process.env.MYCOLLAB_TEST_API_TARGET
  if (!server) throw new Error('请从隔离 Django 验收入口运行')
  const profile = await mkdtemp(path.join(tmpdir(), 'mycollab-desktop-gui-'))
  const app = await electron.launch({
    executablePath: require('../../desktop/node_modules/electron'),
    args: [path.resolve('e2e/desktop-launch.cjs')],
    env: { ...process.env, MYCOLLAB_DESKTOP_TEST_PROFILE: profile },
  })
  const page = await app.firstWindow()
  await app.context().tracing.start({ screenshots: true, snapshots: true })
  try {
    expect(await app.evaluate(({ app }) => app.getPath('userData'))).toBe(profile)
    await expect(page.getByText('桌面设置', { exact: true })).toBeVisible()
    await page.getByPlaceholder('https://collab.example.com').fill(server)
    await page.getByRole('button', { name: '保存服务器并前往登录' }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.getByRole('textbox', { name: '用户名' }).fill('desktop_user')
    await page.locator('input[type=password]').fill('desktop-test-password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(/\/my-work$/)
    await page.getByRole('menuitem', { name: '任务广场', exact: true }).click()
    await expect(page).toHaveURL(/\/missions$/)
    await page.reload()
    await expect(page.getByRole('menuitem', { name: '本地 Agent', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.cookie)).not.toContain('sessionid')
    expect(await page.evaluate(() => typeof (window as unknown as { require?: unknown }).require)).toBe('undefined')
    await page.screenshot({ path: testInfo.outputPath('missions.png'), fullPage: true })
    await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO7sAAAAASUVORK5CYII=', 'base64')
    await page.locator('input[type=file]').setInputFiles({ name: '桌面素材.png', mimeType: 'image/png', buffer: png })
    const fileLink = page.getByRole('link', { name: '桌面素材.png', exact: true })
    await expect(fileLink).toBeVisible()
    const fileURL = await fileLink.getAttribute('href')
    expect(fileURL).toMatch(/^\/api\/library\/files\//)
    const thumbnail = page.locator('.el-table img')
    await expect.poll(() => thumbnail.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(1)
    const bytes = await page.evaluate(async url => Array.from(new Uint8Array(await (await fetch(url!)).arrayBuffer())), fileURL)
    expect(Buffer.from(bytes)).toEqual(png)
    // 这里只替换系统路径选择；点击、IPC、授权请求和流式落盘都走真实产品实现。
    const destination = path.join(profile, '已保存的素材.png')
    await app.evaluate(({ dialog }, filePath) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath })
    }, destination)
    await fileLink.click()
    await expect.poll(async () => (await readFile(destination).catch(() => Buffer.alloc(0))).toString('base64')).toBe(png.toString('base64'))
    await page.screenshot({ path: testInfo.outputPath('library.png'), fullPage: true })
    await page.getByRole('button', { name: '退出', exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.reload()
    await expect(page).toHaveURL(/\/login$/)
    expect(await page.evaluate(async url => (await fetch(url!)).status, fileURL)).toBe(403)
    await page.getByRole('textbox', { name: '用户名' }).fill('desktop_other')
    await page.locator('input[type=password]').fill('desktop-test-password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(/\/my-work$/)
    await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
    await expect(page.getByRole('heading', { name: '我的素材库' })).toBeVisible()
    await expect(page.getByRole('link', { name: '桌面素材.png', exact: true })).toHaveCount(0)
    // 业务规则允许已登录成员读引用素材，但不允许删除别人的素材。
    expect(await page.evaluate(async url => (await fetch(url!)).status, fileURL)).toBe(200)
    expect(await page.evaluate(async url => (await fetch(url!, { method: 'DELETE' })).status, fileURL)).toBe(403)
    expect(await page.evaluate(async () => (await fetch('/api/auth/me/')).status)).toBe(200)
  } catch (error) {
    await page.screenshot({ path: testInfo.outputPath('failure.png'), fullPage: true }).catch(() => {})
    throw error
  } finally {
    await app.context().tracing.stop({ path: testInfo.outputPath('trace.zip') })
    await app.close()
    await rm(profile, { recursive: true, force: true })
  }
})
