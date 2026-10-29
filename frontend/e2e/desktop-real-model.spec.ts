import { test, expect, _electron as electron } from '@playwright/test'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

test('安装客户端通过本机模型生成一次候选并显式保存', async ({}, info) => {
  test.setTimeout(120000)
  const real = process.env.MYCOLLAB_DESKTOP_TEST_SUITE === 'real-model'
  const model = real ? process.env.MYCOLLAB_LIVE_MODEL : process.env.MYCOLLAB_GUI_MODEL
  const cli = real ? process.env.MYCOLLAB_LIVE_OPENCODE : process.env.MYCOLLAB_GUI_OPENCODE
  const binary = process.env.MYCOLLAB_TEST_APP_BINARY
  const server = process.env.MYCOLLAB_TEST_API_TARGET
  if (!model || !cli || !binary || !server) throw new Error('真实模型验收须显式指定模型、CLI、安装副本并从隔离 Django 入口运行。')
  const profile = await mkdtemp(path.join(tmpdir(), 'mycollab-real-model-'))
  const started = Date.now()
  const app = await electron.launch({ executablePath: binary, args: [`--user-data-dir=${profile}`] })
  try {
    expect(await app.evaluate(({ app }) => app.isPackaged)).toBe(true)
    expect(await app.evaluate(({ app }) => app.getPath('userData'))).toBe(profile)
    const page = await app.firstWindow()
    await page.getByPlaceholder('https://collab.example.com').fill(server)
    await page.getByRole('button', { name: '保存服务器并前往登录' }).click()
    await page.getByRole('textbox', { name: '用户名', exact: true }).fill('desktop_user')
    await page.locator('input[type=password]').fill('desktop-test-password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await page.getByRole('menuitem', { name: '本地 Agent', exact: true }).click()
    await page.getByRole('textbox', { name: '设备名称', exact: true }).fill('一次真实模型验收')
    await page.getByRole('button', { name: '创建设备凭据', exact: true }).click()
    await page.getByPlaceholder('provider/model').fill(model)
    await page.getByRole('textbox', { name: 'OpenCode 可执行文件', exact: true }).fill(cli)
    await page.getByRole('button', { name: '验证并加密保存到本机', exact: true }).click()
    await expect(page.getByRole('button', { name: '启动 Runner', exact: true })).toBeEnabled({ timeout: 30000 })
    await page.getByRole('button', { name: '自检（不调用模型）', exact: true }).click()
    await expect(page.getByText('通过', { exact: true })).toHaveCount(2, { timeout: 20000 })
    await page.getByRole('button', { name: '启动 Runner', exact: true }).click()
    await expect(page.getByText('等待任务', { exact: true })).toBeVisible({ timeout: 15000 })
    await page.getByRole('menuitem', { name: '设计与资产', exact: true }).click()
    await page.getByRole('button', { name: '新建条目', exact: true }).click()
    const form = page.getByRole('dialog', { name: '新建设计条目', exact: true })
    const title = '真实模型隔离验收'
    const content = '一份虚构的设计说明：角色穿绿色披风，不添加武器。请简洁润色，保留这两项事实。'
    await form.getByLabel('标题', { exact: true }).fill(title)
    await form.getByLabel('设计内容', { exact: true }).fill(content)
    await form.getByRole('button', { name: '保存', exact: true }).click()
    await expect(form).not.toBeVisible()
    await page.getByRole('link', { name: title, exact: true }).click()
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
    const id = page.url().split('/').pop()!
    const readDesign = () => page.evaluate(async id => (await fetch(`/api/design-elements/${id}/`)).json(), id)
    const before = await readDesign()
    await page.getByRole('button', { name: '编辑', exact: true }).click()
    const edit = page.getByRole('dialog', { name: '编辑设计条目', exact: true })
    await edit.getByRole('button', { name: '预览发送内容', exact: true }).click()
    // 只提交一次，不自动重试真实供应商请求。
    const submitted = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/assistance-requests/'))
    await edit.getByRole('button', { name: '生成候选', exact: true }).click()
    const created = await submitted
    expect(created.status()).toBe(201)
    const requestId = (await created.json()).id as string
    console.log(`${real ? '真实模型' : '假 CLI'}辅助请求已提交一次，不自动重试。`)
    await expect(edit.getByText('候选已返回，尚未保存', { exact: true })).toBeVisible({ timeout: 60000 })
    await expect(edit.getByLabel('设计内容', { exact: true })).toHaveValue(content)
    expect((await readDesign()).version).toBe(before.version)
    const result = await page.evaluate(async id => (await fetch(`/api/assistance-requests/${id}/`)).json(), requestId)
    expect(result.status).toBe('succeeded')
    const candidate = result.result.content as string
    expect(candidate.trim().length).toBeGreaterThan(0)
    await edit.getByRole('button', { name: '采纳说明', exact: true }).click()
    await expect(edit.getByLabel('设计内容', { exact: true })).toHaveValue(candidate)
    expect((await readDesign()).version).toBe(before.version)
    await edit.getByRole('button', { name: '保存', exact: true }).click()
    await expect(edit).not.toBeVisible()
    await page.reload()
    const after = await readDesign()
    expect(after.content).toBe(candidate)
    expect(after.version).toBe(before.version + 1)
    const requests = await page.evaluate(async () => (await fetch('/api/assistance-requests/')).json())
    expect(requests.results).toHaveLength(1)
    expect(requests.results[0].status).toBe('succeeded')
    await page.getByRole('menuitem', { name: '本地 Agent', exact: true }).click()
    await page.getByRole('button', { name: '停止 Runner', exact: true }).click()
    await expect(page.getByText('已停止', { exact: true })).toBeVisible({ timeout: 15000 })
    await writeFile(info.outputPath('acceptance.json'), JSON.stringify({ model: real ? model : 'fixture', realModel: real, platform: process.platform,
      isPackaged: true, requests: 1, succeeded: true, explicitAdoptionAndSave: true,
      runnerStopped: true, elapsedMs: Date.now() - started,
      scope: '隔离 Django 与虚构文本；一次辅助请求；本摘要不包含令牌或模型正文；失败上下文仅含虚构验收材料。',
    }, null, 2) + '\n')
  } finally {
    await app.close()
    await rm(profile, { recursive: true, force: true })
  }
})
