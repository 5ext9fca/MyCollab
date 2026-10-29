import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import html from '../../index.html?raw'
import bootstrap from '../../public/theme-init.js?raw'

let dark = false
let change: (() => void) | undefined
let cleanup: (() => void) | undefined
beforeEach(() => {
  vi.resetModules()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  dark = false
  change = undefined
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    get matches() { return dark },
    addEventListener: (_: string, callback: () => void) => { change = callback },
    removeEventListener: () => { change = undefined },
  })))
})
afterEach(() => {
  cleanup?.()
  cleanup = undefined
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  document.documentElement.style.colorScheme = ''
})
async function setup() {
  const theme = await import('../theme')
  cleanup = theme.initializeTheme()
  return theme
}

describe('外观主题', () => {
  it('默认跟随系统，系统切换立即生效', async () => {
    dark = true
    const theme = await setup()
    expect(theme.themePreference.value).toBe('system')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    dark = false
    change?.()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(document.documentElement.style.colorScheme).toBe('light')
  })
  it('手动选择覆盖系统偏好并在重新初始化后保留', async () => {
    const theme = await setup()
    theme.setThemePreference('dark')
    expect(localStorage.getItem(theme.THEME_STORAGE_KEY)).toBe('dark')
    change?.()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    cleanup?.()
    cleanup = theme.initializeTheme()
    expect(theme.themePreference.value).toBe('dark')
    dark = true
    theme.setThemePreference('light')
    change?.()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    theme.setThemePreference('system')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
  it('同步其他标签页的偏好和清空操作', async () => {
    const theme = await setup()
    localStorage.setItem(theme.THEME_STORAGE_KEY, 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: theme.THEME_STORAGE_KEY }))
    expect(theme.themePreference.value).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    localStorage.clear()
    window.dispatchEvent(new StorageEvent('storage', { key: null }))
    expect(theme.themePreference.value).toBe('system')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
  it('无效偏好回到系统，禁用存储仍能切换', async () => {
    localStorage.setItem('mycollab-theme', 'invalid')
    dark = true
    const theme = await setup()
    expect(theme.themePreference.value).toBe('system')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('存储不可用') })
    expect(() => theme.setThemePreference('light')).not.toThrow()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('存储不可用') })
    cleanup?.()
    cleanup = theme.initializeTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
  it('选择控件可用，更新文档主题和持久化值', async () => {
    await setup()
    const { default: ThemeSelect } = await import('../components/ThemeSelect.vue')
    const wrapper = mount(ThemeSelect)
    const select = wrapper.get('select[aria-label="外观主题"]')
    await select.setValue('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem('mycollab-theme')).toBe('dark')
    await select.setValue('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    wrapper.unmount()
  })
  it('页面引导脚本在应用挂载前恢复深色或跟随系统', () => {
    expect(html).toContain('<script src="/theme-init.js"></script>')
    expect(html.indexOf('/theme-init.js')).toBeLessThan(html.indexOf('/src/main.ts'))
    localStorage.setItem('mycollab-theme', 'dark')
    new Function(bootstrap)()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    localStorage.setItem('mycollab-theme', 'light')
    dark = true
    new Function(bootstrap)()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    localStorage.clear()
    new Function(bootstrap)()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
