import { test, expect, type Browser, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

async function login(page: Page, username: string) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('menuitem', { name: '文件互传', exact: true }).click()
  await expect(page.getByRole('heading', { name: '文件互传', exact: true })).toBeVisible()
}

async function pair(sender: Page, receiver: Page) {
  await sender.getByRole('button', { name: '生成配对码' }).click()
  const code = sender.getByTestId('pair-code')
  await expect(code).toBeVisible()
  await receiver.getByRole('textbox', { name: '配对码', exact: true }).fill((await code.textContent())!)
  await receiver.getByRole('button', { name: '查看待接收文件' }).click()
  await expect(receiver.getByRole('button', { name: '确认接收', exact: true })).toBeVisible()
  await expect(receiver.getByRole('link', { name: '保存已校验文件' })).toHaveCount(0)
}

async function pages(browser: Browser, sameAccount = false) {
  const first = await browser.newContext({ permissions: ['local-network-access'] })
  const second = await browser.newContext({ permissions: ['local-network-access'] })
  const sender = await first.newPage()
  const receiver = await second.newPage()
  await login(sender, 'transfer_sender')
  await login(receiver, sameAccount ? 'transfer_sender' : 'transfer_receiver')
  return { sender, receiver, close: async () => { await first.close(); await second.close() } }
}

for (const bytes of [0, 2 * 1024 * 1024 + 7, 100 * 1024 * 1024]) {
  test(`真实直传 ${bytes} 字节且下载 checksum 一致`, async ({ browser }, info) => {
    if (bytes === 100 * 1024 * 1024) test.setTimeout(180000)
    const { sender, receiver, close } = await pages(browser, bytes === 0)
    const dir = await mkdtemp(join(tmpdir(), 'mycollab-transfer-'))
    try {
      const payload = Buffer.alloc(bytes)
      for (let i = 0; i < bytes; i++) payload[i] = i % 251
      const hash = createHash('sha256').update(payload).digest('hex')
      const path = join(dir, '传输验证.bin')
      await writeFile(path, payload)
      const apiSizes: number[] = []
      for (const page of [sender, receiver]) page.on('request', request => {
        if (request.url().includes('/api/file-transfers/')) apiSizes.push(Buffer.byteLength(request.postData() || ''))
      })
      await sender.locator('input[type=file]').setInputFiles(path)
      await pair(sender, receiver)
      // 未确认接收前不传输文件。
      await expect(sender.getByRole('status')).toContainText('等待接收方确认', { timeout: 10000 })
      await receiver.getByRole('button', { name: '确认接收', exact: true }).click()
      const link = receiver.getByRole('link', { name: '保存已校验文件' })
      await expect(link).toBeVisible({ timeout: bytes === 100 * 1024 * 1024 ? 150000 : 45000 })
      await expect(sender.getByRole('status')).toContainText('传输成功', { timeout: 10000 })
      await expect(receiver.locator('.checksum').last()).toHaveText(hash)
      const download = receiver.waitForEvent('download')
      await link.click()
      const file = await download
      expect(createHash('sha256').update(await readFile((await file.path())!)).digest('hex')).toBe(hash)
      expect(apiSizes.length).toBeGreaterThan(0)
      expect(Math.max(...apiSizes)).toBeLessThan(20000)
      if (bytes > 0 && bytes < 100 * 1024 * 1024) {
        await receiver.screenshot({ path: info.outputPath('verified-desktop.png'), fullPage: true })
        await receiver.setViewportSize({ width: 390, height: 844 })
        await receiver.screenshot({ path: info.outputPath('verified-mobile.png'), fullPage: true })
        expect(await receiver.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      }
    } finally { await close(); await rm(dir, { recursive: true, force: true }) }
  })
}

test('实际传输中的字节被修改时拒绝下载并通知发送方', async ({ browser }) => {
  const { sender, receiver, close } = await pages(browser)
  try {
    await sender.evaluate(() => {
      const original = RTCDataChannel.prototype.send
      let corrupted = false
      RTCDataChannel.prototype.send = function (this: RTCDataChannel, data: string | ArrayBuffer) {
        if (!corrupted && data instanceof ArrayBuffer && data.byteLength) {
          const copy = data.slice(0)
          new Uint8Array(copy)[0] ^= 1
          corrupted = true
          return original.call(this, copy as never)
        }
        return original.call(this, data as never)
      } as typeof RTCDataChannel.prototype.send
    })
    await sender.locator('input[type=file]').setInputFiles({ name: 'checksum.bin', mimeType: 'application/octet-stream', buffer: Buffer.from('checksum validation') })
    await pair(sender, receiver)
    await receiver.getByRole('button', { name: '确认接收', exact: true }).click()
    await expect(receiver.getByRole('status')).toContainText('校验不一致', { timeout: 30000 })
    await expect(sender.getByRole('status')).toContainText('校验不一致', { timeout: 10000 })
    await expect(receiver.getByRole('link', { name: '保存已校验文件' })).toHaveCount(0)
  } finally { await close() }
})

test('接收方可以拒绝，发送方看到取消且可再次发送', async ({ browser }) => {
  const { sender, receiver, close } = await pages(browser)
  try {
    await sender.locator('input[type=file]').setInputFiles({ name: 'cancel.txt', mimeType: 'text/plain', buffer: Buffer.from('cancel') })
    await pair(sender, receiver)
    await receiver.getByRole('button', { name: '取消传输' }).click()
    await expect(sender.getByRole('status')).toContainText('已取消', { timeout: 10000 })
    await expect(sender.getByRole('button', { name: '生成配对码' })).toBeEnabled()
    await expect(receiver.getByRole('link', { name: '保存已校验文件' })).toHaveCount(0)
  } finally { await close() }
})

test('传输中取消会关闭数据通道并丢弃部分文件', async ({ browser }) => {
  const { sender, receiver, close } = await pages(browser)
  try {
    await sender.evaluate(() => {
      const original = RTCDataChannel.prototype.send
      RTCDataChannel.prototype.send = function (this: RTCDataChannel, data: string | ArrayBuffer) {
        original.call(this, data as never)
        if (data instanceof ArrayBuffer) Object.defineProperty(this, 'bufferedAmount', { get: () => 1024 * 1024, configurable: true })
      } as typeof RTCDataChannel.prototype.send
    })
    await sender.locator('input[type=file]').setInputFiles({ name: 'partial.bin', mimeType: 'application/octet-stream', buffer: Buffer.alloc(2 * 1024 * 1024, 42) })
    await pair(sender, receiver)
    await receiver.getByRole('button', { name: '确认接收', exact: true }).click()
    await expect(receiver.getByText(/已处理 16,384 字节/)).toBeVisible({ timeout: 20000 })
    await sender.getByRole('button', { name: '取消传输' }).click()
    await expect(sender.getByRole('status')).toContainText('已取消')
    await expect(receiver.getByRole('status')).toContainText(/已取消|连接中断/, { timeout: 10000 })
    await expect(receiver.getByRole('link', { name: '保存已校验文件' })).toHaveCount(0)
  } finally { await close() }
})
