import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'file-transfer.spec.ts',
  fullyParallel: false,
  workers: 1,
  maxFailures: 1,
  timeout: 60000,
  use: {
    baseURL: 'http://localhost:5179',
    channel: process.env.MYCOLLAB_BROWSER_CHANNEL || undefined,
    // 仅用于诊断本机 mDNS 受限的测试环境，不修改应用的连接配置。
    launchOptions: { args: process.env.MYCOLLAB_TEST_RAW_IP === '1' ? ['--disable-features=WebRtcHideLocalIpsWithMdns'] : [] },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host localhost --port 5179 --strictPort',
    url: 'http://localhost:5179',
    reuseExistingServer: false,
  },
})
