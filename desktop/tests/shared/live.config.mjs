import { defineConfig } from '@playwright/test'

if (process.platform !== 'win32' || !process.env.MYCOLLAB_ACCEPTANCE_SERVER) {
  throw new Error('真实站点验收须从 Windows 本地入口显式指定 LiveServer。')
}
const server = new URL(process.env.MYCOLLAB_ACCEPTANCE_SERVER)
if (server.protocol !== 'https:' || server.username || server.password || server.pathname !== '/' || server.search || server.hash) {
  throw new Error('LiveServer 须为 HTTPS 根地址，不接受凭据或查询参数。')
}
export default defineConfig({
  testDir: '.', testMatch: 'live.spec.mjs', workers: 1, retries: 0,
  timeout: 900000, globalTimeout: 960000, expect: { timeout: 15000 },
  outputDir: 'results/artifacts',
  reporter: [['list'], ['html', { outputFolder: 'results/html', open: 'never' }],
    ['json', { outputFile: 'results/results.json' }]],
})
