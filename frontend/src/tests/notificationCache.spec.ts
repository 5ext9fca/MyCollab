import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, it, expect, vi } from 'vitest'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import { notificationSummary } from '../api/notifications'
vi.mock('../api/notifications', () => ({ notificationSummary: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ name: 'my-work' }), useRouter: () => ({ push: vi.fn() }) }))
const slot = { template: '<div><slot /></div>' }
describe('账户通知缓存', () => {
  it('切换账户清零，忽略旧账户尚未完成的摘要响应', async () => {
    setActivePinia(createPinia())
    const auth = useAuthStore(); auth.user = { id: 1 } as never
    let old!: (value: { unread_count: number }) => void
    vi.mocked(notificationSummary).mockImplementationOnce(() => new Promise(resolve => { old = resolve })).mockResolvedValue({ unread_count: 2 })
    const wrapper = mount(AppLayout, { global: { stubs: { ElContainer: slot, ElHeader: slot, ElMenu: slot, ElMenuItem: slot, ElMain: slot, ElButton: true, RouterView: true } } })
    auth.user = { id: 2 } as never; await flushPromises()
    expect(wrapper.text()).toContain('通知 2')
    old({ unread_count: 99 }); await flushPromises()
    expect(wrapper.text()).not.toContain('99')
    auth.user = null; await flushPromises(); expect(wrapper.text()).not.toContain('通知 2')
    wrapper.unmount()
  })
})
