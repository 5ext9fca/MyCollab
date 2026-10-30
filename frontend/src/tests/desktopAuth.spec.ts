import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../stores/auth'

const mocks = vi.hoisted(() => ({ logout: vi.fn(), login: vi.fn() }))
vi.mock('../platform/desktop', () => ({ desktop: {} }))
vi.mock('../api/auth', () => ({ logout: mocks.logout, login: mocks.login }))
beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })
afterEach(() => vi.unstubAllGlobals())

it('宿主停止失败时保留用户与页面，不假装已经退出', async () => {
  const replace = vi.fn()
  vi.stubGlobal('window', { location: { replace } })
  const user = { id: 1, username: 'owner' }
  mocks.login.mockResolvedValue(user)
  mocks.logout.mockRejectedValue(Error('Runner 尚未停止'))
  const store = useAuthStore()
  await store.login('owner', 'unused')
  await expect(store.logout()).rejects.toThrow('Runner 尚未停止')
  expect(store.user).toEqual(user)
  expect(replace).not.toHaveBeenCalled()
})

it('宿主确认退出后才丢弃用户并重载登录页', async () => {
  const replace = vi.fn()
  vi.stubGlobal('window', { location: { replace } })
  mocks.login.mockResolvedValue({ id: 1, username: 'owner' })
  mocks.logout.mockResolvedValue(undefined)
  const store = useAuthStore()
  await store.login('owner', 'unused')
  await store.logout()
  expect(store.user).toBeNull()
  expect(replace).toHaveBeenCalledWith('/login')
})
