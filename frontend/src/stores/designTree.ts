import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useAuthStore } from './auth'

// 只保留当前登录会话的展开状态；页面切换保留，身份变化清空，不落盘。
export const useDesignTreeStore = defineStore('design-tree', () => {
  const expanded = ref(new Set<string>())
  const auth = useAuthStore()
  watch(() => auth.user?.id, () => { expanded.value = new Set() }, { flush: 'sync' })
  function toggle(id: string) {
    if (expanded.value.has(id)) expanded.value.delete(id)
    else expanded.value.add(id)
  }
  return { expanded, toggle }
})
