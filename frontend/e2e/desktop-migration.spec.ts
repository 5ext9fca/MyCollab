import { test, expect, _electron as electron } from '@playwright/test'
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from 'node:fs/promises'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { once } from 'node:events'

const require = createRequire(import.meta.url)
test('源码宿主隔离导入旧伴侣配置并复用设备锁', async ({}, info) => {
  test.skip(process.platform !== 'darwin', '旧伴侣迁移仅适用于 macOS')
  const server = process.env.MYCOLLAB_TEST_API_TARGET
  if (!server) throw new Error('需要隔离 Django 验收入口')
  const root = await mkdtemp(path.join(tmpdir(), 'mycollab-migration-'))
  const home = path.join(root, '旧用户目录')
  const legacy = path.join(home, '.config/MyCollab/mycollab-runner.json')
  const profile = path.join(root, '新客户端')
  await mkdir(path.dirname(legacy), { recursive: true })
  await mkdir(profile)
  const app = await electron.launch({
    executablePath: require('../../desktop/node_modules/electron'),
    args: [path.resolve('e2e/desktop-launch.cjs')],
    env: { ...process.env, MYCOLLAB_DESKTOP_TEST_PROFILE: profile, MYCOLLAB_DESKTOP_TEST_HOME: home },
  })
  let old: ChildProcessWithoutNullStreams | undefined
  try {
    await app.context().tracing.start({ screenshots: true, snapshots: true })
    expect(await app.evaluate(({ app }) => app.getPath('home'))).toBe(home)
    expect(await app.evaluate(({ app }) => app.isPackaged)).toBe(false)
    const page = await app.firstWindow()
    await page.getByPlaceholder('https://collab.example.com').fill(server)
    await page.getByRole('button', { name: '保存服务器并前往登录' }).click()
    await page.getByRole('textbox', { name: '用户名' }).fill('desktop_other')
    await page.locator('input[type=password]').fill('desktop-test-password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await page.getByRole('menuitem', { name: '本地 Agent', exact: true }).click()
    await page.getByRole('textbox', { name: '设备名称', exact: true }).fill('旧伴侣迁移验收设备')
    await page.getByRole('button', { name: '创建设备凭据', exact: true }).click()
    const token = await page.getByRole('textbox', { name: '设备凭据', exact: true }).inputValue()
    const config = { server, device_token: token, model: 'test/migration', opencode: path.join(root, '不存在的 CLI') }
    const original = JSON.stringify(config)
    await writeFile(legacy, original, { mode: 0o600 })
    const runner = path.resolve(`../desktop/build/runner/mac-${process.arch}/mycollab-runner`)
    old = spawn(runner, ['--config', legacy, '--config-stdin', '--control-stdin', '--desktop-events'])
    old.stderr.resume()
    const oldClosed = once(old, 'close')
    const ready = new Promise<void>((resolve, reject) => {
      let output = ''
      const timer = setTimeout(() => reject(new Error('旧 Runner 未就绪')), 15000)
      old!.once('error', error => { clearTimeout(timer); reject(error) })
      old!.once('close', () => { clearTimeout(timer); reject(new Error('旧 Runner 提前退出')) })
      old!.stdout.on('data', chunk => {
        output += chunk.toString()
        if (output.includes('"ready"')) { clearTimeout(timer); resolve() }
      })
    })
    old.stdin.write(original + '\n')
    await ready
    await page.getByRole('button', { name: '导入旧伴侣配置', exact: true }).click()
    await expect(page.getByPlaceholder('provider/model')).toHaveValue('test/migration')
    await expect(page.getByRole('textbox', { name: '设备令牌', exact: true })).toHaveValue('')
    expect(await readFile(legacy, 'utf8')).toBe(original)
    const encrypted = (await readdir(path.join(profile, 'devices'))).filter(name => name.endsWith('.encrypted'))
    expect(encrypted).toHaveLength(1)
    expect((await readFile(path.join(profile, 'devices', encrypted[0]!))).includes(Buffer.from(token))).toBe(false)
    await page.getByRole('button', { name: '启动 Runner', exact: true }).click()
    await expect(page.getByText('Runner 操作失败，请检查设备有效期、OpenCode 配置和网络。尚未停止时不能切换身份。', { exact: true })).toBeVisible({ timeout: 20000 })
    expect(old.exitCode).toBeNull()
    old.stdin.end()
    await oldClosed
    old = undefined
    await page.getByRole('button', { name: '启动 Runner', exact: true }).click()
    await expect(page.getByText('等待任务', { exact: true })).toBeVisible({ timeout: 20000 })
    expect(await readFile(legacy, 'utf8')).toBe(original)
    expect(await readdir(path.join(path.dirname(legacy), 'runner-state'))).toHaveLength(1)
    await page.getByRole('button', { name: '停止 Runner', exact: true }).click()
    await expect(page.getByText('已停止', { exact: true })).toBeVisible({ timeout: 15000 })
    await page.reload()
    await expect(page.getByPlaceholder('provider/model')).toHaveValue('test/migration')
    await page.screenshot({ path: info.outputPath('migration.png'), fullPage: true })
  } finally {
    if (old && old.exitCode === null) {
      const closed = once(old, 'close')
      old.stdin.end()
      await closed
    }
    await app.context().tracing.stop({ path: info.outputPath('trace.zip') }).catch(() => {})
    await app.close()
    await rm(root, { recursive: true, force: true })
  }
})
