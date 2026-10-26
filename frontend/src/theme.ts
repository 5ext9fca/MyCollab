import { readonly, ref } from 'vue'

export type ThemePreference = 'system' | 'light' | 'dark'
export const THEME_STORAGE_KEY = 'mycollab-theme'

function normalize(value: string | null): ThemePreference {
  return value === 'light' || value === 'dark' ? value : 'system'
}
function readPreference(): ThemePreference {
  try { return normalize(localStorage.getItem(THEME_STORAGE_KEY)) }
  catch { return 'system' }
}

const preference = ref<ThemePreference>(readPreference())
let media: MediaQueryList | undefined
export const themePreference = readonly(preference)

function applyTheme() {
  const dark = preference.value === 'dark' || (preference.value === 'system' && !!media?.matches)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

export function setThemePreference(value: ThemePreference) {
  preference.value = normalize(value)
  try { localStorage.setItem(THEME_STORAGE_KEY, preference.value) }
  catch { /* 浏览器禁用存储时，仍允许本次访问切换主题。 */ }
  applyTheme()
}

/** 应用启动时调用一次；返回清理函数供热更新与测试使用。 */
export function initializeTheme() {
  media = window.matchMedia?.('(prefers-color-scheme: dark)')
  preference.value = readPreference()
  applyTheme()
  const onSystemChange = () => applyTheme()
  const onStorage = (event: StorageEvent) => {
    if (event.key !== THEME_STORAGE_KEY && event.key !== null) return
    preference.value = readPreference()
    applyTheme()
  }
  media?.addEventListener('change', onSystemChange)
  window.addEventListener('storage', onStorage)
  return () => {
    media?.removeEventListener('change', onSystemChange)
    window.removeEventListener('storage', onStorage)
  }
}
