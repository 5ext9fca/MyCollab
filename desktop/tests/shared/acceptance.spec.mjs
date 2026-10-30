import { mkdir, readFile, readdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { test, expect } from './fixtures.mjs'
import { names, payload } from './server.mjs'

test('刷新保持会话，重启同一测试配置后重新登录', async ({ desktop }) => {
  await desktop.page.reload()
  await expect(desktop.page.getByRole('menuitem', { name: '素材库', exact: true })).toBeVisible()
  expect(await desktop.page.evaluate(() => document.cookie)).not.toContain('sessionid')
  await desktop.restart()
  await expect(desktop.page).toHaveURL(/\/login(?:\?|$)/)
})

test('关闭隐藏窗口，恢复后保留未提交输入', async ({ desktop }) => {
  const { page, app } = desktop
  await page.getByRole('menuitem', { name: '设计与资产', exact: true }).click()
  const input = page.getByPlaceholder('搜索设计或资产的标题与正文')
  await input.fill('未提交的测试输入')
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close())
  await expect.poll(() => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isVisible())).toBe(false)
  // 通过宿主事件恢复，不能替代真实 Windows 托盘鼠标交互。
  await app.evaluate(({ app }) => app.emit('activate'))
  await expect.poll(() => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isVisible())).toBe(true)
  await expect(input).toHaveValue('未提交的测试输入')
})

test('开发包更新按钮禁用且渲染进程不暴露 Node', async ({ desktop }) => {
  await desktop.page.getByRole('link', { name: '桌面设置', exact: true }).click()
  await expect(desktop.page.getByText('此开发包未启用在线更新', { exact: true })).toBeVisible()
  for (const name of ['检查更新', '下载更新', '停止 Runner 并安装更新']) {
    await expect(desktop.page.getByRole('button', { name, exact: true })).toBeDisabled()
  }
  expect(await desktop.page.evaluate(() => typeof window.require)).toBe('undefined')
})

for (const name of names) {
  test(`素材真实落盘与 SHA-256：${name}`, async ({ desktop }, info) => {
    const { app, page, profile } = desktop
    await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
    const destination = path.join(profile, 'download.txt')
    // 仅替换原生路径选择，链接、IPC、HTTP 下载和磁盘写入均为产品实现。
    await app.evaluate(({ dialog }, destination) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: destination })
    }, destination)
    await page.getByRole('link', { name, exact: true }).click()
    await expect.poll(async () => (await readFile(destination).catch(() => Buffer.alloc(0))).toString('base64')).toBe(payload.toString('base64'))
    const digest = data => createHash('sha256').update(data).digest('hex')
    await info.attach('文件摘要', { body: JSON.stringify({ name, bytes: payload.length,
      source: digest(payload), destination: digest(await readFile(destination)) }), contentType: 'application/json' })
  })
}

test('取消保存不产生文件，随后仍能保存', async ({ desktop }) => {
  const { app, page, profile } = desktop
  await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
  const before = (await readdir(profile)).sort()
  await app.evaluate(({ dialog }) => {
    globalThis.acceptanceSaveCalls = 0
    dialog.showSaveDialog = async () => { globalThis.acceptanceSaveCalls++; return { canceled: true } }
  })
  await page.getByRole('link', { name: names[1], exact: true }).click()
  await expect.poll(() => app.evaluate(() => globalThis.acceptanceSaveCalls)).toBe(1)
  // 直接等待第二次 IPC 返回，保证第一次取消分支已完成；不靠固定 sleep 猜测落盘时机。
  const url = await page.getByRole('link', { name: names[1], exact: true }).getAttribute('href')
  expect(await page.evaluate(url => window.mycollabDesktop.downloadLibrary(new URL(url, location.href).href), url)).toBe(false)
  const after = await readdir(profile)
  expect(after.filter(name => name.endsWith('.partial') || name === 'download.txt')).toEqual([])
  expect(before).not.toContain('download.txt')
  const destination = path.join(profile, 'download.txt')
  await app.evaluate(({ dialog }, destination) => { dialog.showSaveDialog = async () => ({ canceled: false, filePath: destination }) }, destination)
  await page.getByRole('link', { name: names[1], exact: true }).click()
  await expect.poll(async () => (await readFile(destination).catch(() => Buffer.alloc(0))).toString()).toBe(payload.toString())
})

for (const scenario of ['服务器拒绝下载', '保存目标为目录']) {
  test(`下载失败提示与恢复：${scenario}`, async ({ desktop }) => {
    const { app, page, profile } = desktop
    await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
    const blocked = path.join(profile, 'blocked')
    await mkdir(blocked)
    await app.evaluate(({ dialog }, destination) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: destination })
    }, blocked)
    desktop.setDownloadFailure(scenario === '服务器拒绝下载')
    const link = page.getByRole('link', { name: names[1], exact: true })
    await link.click()
    await expect(page.getByText('无法打开链接或保存文件，请检查网络、权限和登录状态。', { exact: true })).toBeVisible()
    expect((await readdir(profile)).filter(name => name.endsWith('.partial'))).toEqual([])
    expect(await readdir(blocked)).toEqual([])
    desktop.setDownloadFailure(false)
    const destination = path.join(profile, 'recovered.txt')
    await app.evaluate(({ dialog }, destination) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: destination })
    }, destination)
    await link.click()
    await expect.poll(async () => (await readFile(destination).catch(() => Buffer.alloc(0))).toString()).toBe(payload.toString())
    expect(await page.evaluate(async () => (await fetch('/api/auth/me/')).status)).toBe(200)
  })
}

for (const name of names) {
  test(`默认下载名称应保留：${name}`, async ({ desktop }) => {
    const { page, app } = desktop
    await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
    await app.evaluate(({ dialog }) => {
      globalThis.acceptanceDefaultName = null
      dialog.showSaveDialog = async (_window, options) => {
        globalThis.acceptanceDefaultName = options.defaultPath
        return { canceled: true }
      }
    })
    await page.getByRole('link', { name, exact: true }).click()
    await expect.poll(() => app.evaluate(() => globalThis.acceptanceDefaultName)).not.toBeNull()
    expect(await app.evaluate(() => globalThis.acceptanceDefaultName)).toBe(name)
  })
}

test('离开设计页面再返回应保留树展开状态', async ({ desktop }) => {
  const { page } = desktop
  await page.getByRole('menuitem', { name: '设计与资产', exact: true }).click()
  const toggle = page.getByRole('button', { name: '展开或折叠验收父设计', exact: true })
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByRole('link', { name: '验收子设计', exact: true })).toBeVisible()
  await page.getByRole('menuitem', { name: '素材库', exact: true }).click()
  await expect(page.getByRole('heading', { name: '我的素材库' })).toBeVisible()
  await page.getByRole('menuitem', { name: '设计与资产', exact: true }).click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByRole('link', { name: '验收子设计', exact: true })).toBeVisible()
})
