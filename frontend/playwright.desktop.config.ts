import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: process.env.MYCOLLAB_DESKTOP_TRANSFER_TEST === '1' ? 'desktop-transfer.spec.ts' : ['desktop.spec.ts', 'desktop-migration.spec.ts'], workers: 1, fullyParallel: false,
  timeout: 90000, outputDir: 'test-results/desktop',
})
