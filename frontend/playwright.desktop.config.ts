import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: 'desktop.spec.ts', workers: 1, fullyParallel: false,
  timeout: 90000, outputDir: 'test-results/desktop',
})
