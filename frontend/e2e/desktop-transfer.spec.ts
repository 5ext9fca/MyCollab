import { test, expect, _electron as electron, type ElectronApplication } from '@playwright/test'
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'

const require = createRequire(import.meta.url)
const fileBytes = Number(process.env.MYCOLLAB_DESKTOP_TRANSFER_BYTES ?? 2097159)
if (![0, 2097159, 104857600].includes(fileBytes)) throw new Error('直传验收大小仅允许 0、2097159 或 104857600 字节')
test(`两个真实桌面会话使用${process.env.MYCOLLAB_TEST_RAW_IP === '1' ? '原始 IP 对照' : '默认 WebRTC'}配置直传 ${fileBytes} 字节并校验文件`, async ({}, info) => {
  test.setTimeout(120000)
  const server = process.env.MYCOLLAB_TEST_API_TARGET
  if (!server) throw new Error('请从隔离 Django 验收入口运行')
  const profiles: string[] = []
  const apps: ElectronApplication[] = []
  const memory: { elapsedMs: number; peers: { type: string; workingSetKB: number }[][] }[] = []
  let sampling = false
  let sampler: Promise<void> | undefined
  let sampleErrors = 0
  let verified = false
  let started = 0
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
    started = performance.now()
    sampling = true
    // 仅采样宿主暴露的原生统计，不读取文件正文或候选地址；顺序采样避免请求重叠。
    sampler = (async () => {
      while (sampling) {
        try {
          const peers = await Promise.all(apps.map(app => app.evaluate(({ app }) => app.getAppMetrics().map((item: { type: string; memory: { workingSetSize: number } }) => ({ type: item.type, workingSetKB: item.memory.workingSetSize })))))
          memory.push({ elapsedMs: Math.round(performance.now() - started), peers })
        } catch { sampleErrors++ }
        if (sampling) await new Promise(resolve => setTimeout(resolve, 250))
      }
    })()
    const payload = Buffer.alloc(fileBytes, 42)
    const checksum = createHash('sha256').update(payload).digest('hex')
    const source = path.join(profiles[0]!, '桌面直传.bin')
    await writeFile(source, payload)
    await sender.locator('input[type=file]').setInputFiles(source)
    await sender.getByRole('button', { name: '生成配对码' }).click()
    const code = sender.getByTestId('pair-code')
    await expect(code).toBeVisible()
    await receiver.getByRole('textbox', { name: '配对码', exact: true }).fill((await code.textContent())!)
    await receiver.getByRole('button', { name: '查看待接收文件' }).click()
    await expect(sender.getByRole('status')).toContainText('等待接收方确认', { timeout: 10000 })
    await receiver.getByRole('button', { name: '确认接收', exact: true }).click()
    const link = receiver.getByRole('link', { name: '保存已校验文件' })
    await expect(link).toBeVisible({ timeout: fileBytes === 104857600 ? 90000 : 45000 })
    await expect(sender.getByRole('status')).toContainText('传输成功', { timeout: 10000 })
    await expect(receiver.locator('.checksum').last()).toHaveText(checksum)
    const destination = path.join(profiles[1]!, '接收的文件.bin')
    // 仅固定测试保存位置，实际 Blob 下载仍交给产品 Session 与 Chromium。
    await apps[1]!.evaluate(({ BrowserWindow }, filePath) => {
      BrowserWindow.getAllWindows()[0]!.webContents.session.once('will-download', (_event: unknown, item: { setSavePath: (path: string) => void }) => item.setSavePath(filePath))
    }, destination)
    await link.click()
    await expect.poll(() => readFile(destination).then(data => createHash('sha256').update(data).digest('hex')).catch(() => null)).toBe(checksum)
    verified = true
    await receiver.screenshot({ path: info.outputPath('received.png'), fullPage: true })
  } finally {
    sampling = false
    await sampler
    const totals = memory.map(sample => sample.peers.map(peer => peer.reduce((sum, process) => sum + process.workingSetKB, 0)))
    try {
      await writeFile(info.outputPath('transfer-performance.json'), JSON.stringify({
        platform: process.platform, arch: process.arch, fileBytes,
        rawIpTestOnly: process.env.MYCOLLAB_TEST_RAW_IP === '1', packaged: Boolean(process.env.MYCOLLAB_TEST_APP_BINARY),
        verified, sampleErrors, samples: memory,
        sampledPeakWorkingSetKB: apps.map((_, index) => totals.length ? Math.max(...totals.map(sample => sample[index]!)) : null),
        scope: '同机双会话，选文件至下载校验结束的离散采样峰值；共享页可能重复计入，不能替代真实双机或系统独占内存。',
      }, null, 2) + '\n')
    } finally {
      for (const [index, app] of apps.entries()) {
        await app.context().tracing.stop({ path: info.outputPath(`peer-${index}.zip`) }).catch(() => {})
        await app.evaluate(({ BrowserWindow }) => { for (const window of BrowserWindow.getAllWindows()) window.destroy() }).catch(() => {})
        await app.close()
      }
      for (const profile of profiles) await rm(profile, { recursive: true, force: true })
    }
  }
  expect(sampleErrors).toBe(0)
  expect(memory.length).toBeGreaterThan(0)
})
