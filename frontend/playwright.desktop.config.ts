import { defineConfig } from '@playwright/test'
const suite = process.env.MYCOLLAB_DESKTOP_TEST_SUITE
const businessTests = ['real-model', 'model-contract'].includes(suite || '') ? ['desktop-real-model.spec.ts'] : suite === 'migration' ? ['desktop-migration.spec.ts']
  : suite === 'packaged' ? ['desktop.spec.ts'] : ['desktop.spec.ts', 'desktop-migration.spec.ts']
export default defineConfig({
  testDir: './e2e', testMatch: process.env.MYCOLLAB_DESKTOP_TRANSFER_TEST === '1' ? 'desktop-transfer.spec.ts' : businessTests, workers: 1, fullyParallel: false,
  timeout: 90000, outputDir: 'test-results/desktop',
})
