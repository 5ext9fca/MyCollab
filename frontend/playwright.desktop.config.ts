import { defineConfig } from '@playwright/test'
const suite = process.env.MYCOLLAB_DESKTOP_TEST_SUITE
const artifactGroup = process.env.MYCOLLAB_DESKTOP_TEST_ARTIFACT_GROUP
if (artifactGroup && !['ci-packaged', 'ci-installed'].includes(artifactGroup)) throw new Error('未知桌面验收产物分组')
if (artifactGroup && !['migration', 'packaged'].includes(suite || '')) throw new Error('CI 产物分组必须配合明确的迁移或打包业务套件')
// Playwright 启动时清理 outputDir；不同宿主及套件不能共用同一目录。
const outputDir = artifactGroup ? `test-results/desktop/${artifactGroup}/${suite}` : 'test-results/desktop'
const businessTests = ['real-model', 'model-contract'].includes(suite || '') ? ['desktop-real-model.spec.ts'] : suite === 'migration' ? ['desktop-migration.spec.ts']
  : suite === 'packaged' ? ['desktop.spec.ts'] : ['desktop.spec.ts', 'desktop-migration.spec.ts']
export default defineConfig({
  testDir: './e2e', testMatch: process.env.MYCOLLAB_DESKTOP_TRANSFER_TEST === '1' ? 'desktop-transfer.spec.ts' : businessTests, workers: 1, fullyParallel: false,
  timeout: 90000, outputDir,
})
