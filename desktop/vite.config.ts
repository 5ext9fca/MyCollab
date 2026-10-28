import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], clearScreen: false, test: { environment: 'jsdom', include: ['src/**/*.spec.ts'] } })
