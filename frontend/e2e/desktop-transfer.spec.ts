import { test, expect, _electron as electron, type ElectronApplication } from '@playwright/test'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'

const require = createRequire(import.meta.url)
test(`两个真实桌面会话使用${process.env.MYCOLLAB_TEST_RAW_IP === '1' ? '原始 IP 对照' : '默认 WebRTC'}配置直传并校验文件`, async ({}, info) => {
  const server = process.env.MYCOLLAB_TEST_API_TARGET
  if (!server) throw new Error('请从隔离 Django 验收入口运行')
  const profiles: string[] = []
  const apps: ElectronApplication[] = []
  try {
    for (const username of ['desktop_user', 'desktop_other']) {
      const profile = await mkdtemp(path.join(tmpdir(), 'mycollab-desktop-transfer-'))
      profiles.push(profile)
      const app = await electron.launch({
        executablePath: process.env.MYCOLLAB_TEST_APP_BINARY || require('../../desktop/node_modules/electron'),
        args: [...(process.env.MYCOLLAB_TEST_APP_BINARY ? [`--user-data-dir=${profile}`] : [path.resolve('e2e/desktop-launch.cjs')]), ...(process.env.MYCOLLAB_TEST_RAW_IP === '1' ? ['--disable-features=WebRtcHideLocalIpsWithMdns'] : [])],
        env: { ...process.env, MYCOLLAB_DESKTOP_TEST_PROFILE: profile },
      })
      apps.push(app)
      expect(await app.evaluate(({ app }) => app.getPath('userData'))).toBe(profile)
      expect(await app.evaluate(({ app }) => app.isPackaged)).toBe(Boolean(process.env.MYCOLLAB_TEST_APP_BINARY))
      await app.context().tracing.start({ screenshots: true, snapshots: true })
      const page = await app.firstWindow()
      await page.getByPlaceholder('https://collab.example.com').fill(server)
      await page.locator('.el-switch').first().click()
      await page.getByRole('button', { name: '保存服务器并前往登录' }).click()
      await page.getByRole('textbox', { name: '用户名' }).fill(username)
      await page.locator('input[type=password]').fill('desktop-test-password')
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await page.getByRole('menuitem', { name: '文件互传', exact: true }).click()
    }
    const sender = await apps[0]!.firstWindow()
    const receiver = await apps[1]!.firstWindow()
    const payload = Buffer.alloc(2 * 1024 * 1024 + 7, 42)
    const checksum = createHash('sha256').update(payload).digest('hex')
    await sender.locator('input[type=file]').setInputFiles({ name: '桌面直传.bin', mimeType: 'application/octet-stream', buffer: payload })
    await sender.getByRole('button', { name: '生成配对码' }).click()
    const code = sender.getByTestId('pair-code')
    await expect(code).toBeVisible()
    await receiver.getByRole('textbox', { name: '配对码', exact: true }).fill((await code.textContent())!)
    await receiver.getByRole('button', { name: '查看待接收文件' }).click()
    await expect(sender.getByRole('status')).toContainText('等待接收方确认', { timeout: 10000 })
    await receiver.getByRole('button', { name: '确认接收', exact: true }).click()
    const link = receiver.getByRole('link', { name: '保存已校验文件' })
    await expect(link).toBeVisible({ timeout: 45000 })
    await expect(sender.getByRole('status')).toContainText('传输成功', { timeout: 10000 })
    await expect(receiver.locator('.checksum').last()).toHaveText(checksum)
    const destination = path.join(profiles[1]!, '接收的文件.bin')
    // 仅固定测试保存位置，实际 Blob 下载仍交给产品 Session 与 Chromium。
    await apps[1]!.evaluate(({ BrowserWindow }, filePath) => {
      BrowserWindow.getAllWindows()[0]!.webContents.session.once('will-download', (_event: unknown, item: { setSavePath: (path: string) => void }) => item.setSavePath(filePath))
    }, destination)
    await link.click()
    await expect.poll(async () => createHash('sha256').update(await readFile(destination).catch(() => Buffer.alloc(0))).digest('hex')).toBe(checksum)
    await receiver.screenshot({ path: info.outputPath('received.png'), fullPage: true })
  } finally {
    for (const [index, app] of apps.entries()) {
      await app.context().tracing.stop({ path: info.outputPath(`peer-${index}.zip`) }).catch(() => {})
      await app.evaluate(({ BrowserWindow }) => { for (const window of BrowserWindow.getAllWindows()) window.destroy() }).catch(() => {})
      await app.close()
    }
    for (const profile of profiles) await rm(profile, { recursive: true, force: true })
  }
})
