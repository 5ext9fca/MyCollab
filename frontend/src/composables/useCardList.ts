import { computed, onUnmounted, ref, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { QueryParams } from '../api/client'
import type { Paginated } from '../api/types'

// 查询包含筛选与排序；固定业务范围由调用者合并，分页参数由列表统一管理。
export function useCardList<T>(query: () => QueryParams, fetchPage: (params: QueryParams) => Promise<Paginated<T>>, initialPageSize = 20) {
  const items = shallowRef<T[]>([]), total = ref(0), loading = ref(false)
  const page = ref(1), pageSize = ref(initialPageSize)
  const queryKey = computed(() => JSON.stringify(query()))
  const resetKey = computed(() => JSON.stringify([queryKey.value, page.value, pageSize.value]))
  let generation = 0
  async function reload() {
    const token = ++generation
    loading.value = true
    items.value = []
    try {
      const data = await fetchPage({ ...query(), page: page.value, page_size: pageSize.value })
      if (token === generation) { items.value = data.results; total.value = data.count }
    } catch (error) {
      if (token === generation) ElMessage.error(error instanceof Error ? error.message : '列表加载失败')
    } finally { if (token === generation) loading.value = false }
  }
  watch([queryKey, pageSize], () => { page.value = 1 }, { flush: 'sync' })
  watch(resetKey, reload, { immediate: true })
  onUnmounted(() => { generation++ })
  return { items, total, loading, page, pageSize, resetKey, reload }
}
