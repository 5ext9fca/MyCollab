import { defineConfig } from '@playwright/test'

if (!['darwin', 'win32'].includes(process.env.MYCOLLAB_TEST_PLATFORM) || process.platform !== process.env.MYCOLLAB_TEST_PLATFORM) {
  throw new Error('请使用与当前系统匹配的 local-macos 或 local-windows 入口。')
}
if (!process.env.MYCOLLAB_TEST_APP_BINARY) throw new Error('需要指定已安装的开发版客户端可执行文件。')

export default defineConfig({
  testDir: '.', testMatch: 'acceptance.spec.mjs', workers: 1, fullyParallel: false,
  timeout: 45000, globalTimeout: 600000, retries: 0,
  expect: { timeout: 5000 }, outputDir: 'results/artifacts',
  reporter: [['list'], ['html', { outputFolder: 'results/html', open: 'never' }],
    ['json', { outputFile: 'results/results.json' }]],
})
