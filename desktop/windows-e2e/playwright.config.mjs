import { defineConfig } from '@playwright/test'

if (process.platform !== 'win32') throw new Error('请在 Windows Node 中运行此套件；WSL 请使用 run.ps1 入口。')
if (!process.env.MYCOLLAB_TEST_APP_BINARY) throw new Error('需要指定已安装的 MyCollab.exe。')

export default defineConfig({
  testDir: '.', testMatch: '*.spec.mjs', workers: 1, fullyParallel: false,
  timeout: 45000, globalTimeout: 600000, retries: 0,
  expect: { timeout: 5000 }, outputDir: 'results/artifacts',
  reporter: [['list'], ['html', { outputFolder: 'results/html', open: 'never' }],
    ['json', { outputFile: 'results/results.json' }]],
})
