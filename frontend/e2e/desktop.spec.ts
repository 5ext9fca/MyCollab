import { test, expect, _electron as electron } from '@playwright/test'
import { mkdtemp, rm } from 'node:fs/promises'
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
    await page.getByRole('button', { name: '退出', exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.reload()
    await expect(page).toHaveURL(/\/login$/)
  } catch (error) {
    await page.screenshot({ path: testInfo.outputPath('failure.png'), fullPage: true }).catch(() => {})
    throw error
  } finally {
    await app.context().tracing.stop({ path: testInfo.outputPath('trace.zip') })
    await app.close()
    await rm(profile, { recursive: true, force: true })
  }
})
