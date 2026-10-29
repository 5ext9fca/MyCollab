import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDesignTreeStore } from '../stores/designTree'
import { useAuthStore } from '../stores/auth'

describe('设计树会话状态', () => {
  it('页面重新获取状态仍保持展开，折叠可移除', () => {
    setActivePinia(createPinia())
    const state = useDesignTreeStore()
    state.toggle('parent')
    expect(useDesignTreeStore().expanded.has('parent')).toBe(true)
    useDesignTreeStore().toggle('parent')
    expect(state.expanded.has('parent')).toBe(false)
  })
  it('同一身份刷新不丢失，退出或切换账户清空', () => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.user = { id: 1, username: 'first', display_name: '甲', is_staff: false }
    const state = useDesignTreeStore()
    state.toggle('private-node')
    auth.user = { ...auth.user }
    expect(state.expanded.has('private-node')).toBe(true)
    auth.user = { id: 2, username: 'second', display_name: '乙', is_staff: false }
    expect(state.expanded.size).toBe(0)
    state.toggle('other-node')
    auth.user = null
    expect(state.expanded.size).toBe(0)
  })
})
