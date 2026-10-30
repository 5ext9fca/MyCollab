import { defineStore } from 'pinia'
import { ref } from 'vue'

import { desktop } from '../platform/desktop'
import * as authApi from '../api/auth'
import type { CurrentUser } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const ready = ref(false)

  async function fetchMe(): Promise<void> {
    try {
      user.value = await authApi.me()
    } catch {
      user.value = null
    } finally {
      ready.value = true
    }
  }

  async function login(username: string, password: string): Promise<void> {
    user.value = await authApi.login(username, password)
    ready.value = true
  }

  async function logout(): Promise<void> {
    if (desktop) {
      // 宿主仅在 Runner 已停止、会话已清理后确认退出；失败时保留页面身份。
      await authApi.logout()
      user.value = null
      window.location.replace('/login')
      return
    }
    try {
      await authApi.logout()
    } finally {
      user.value = null
    }
  }

  return { user, ready, fetchMe, login, logout }
})
