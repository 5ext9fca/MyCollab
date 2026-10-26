<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getDesignElement, listDesignElements } from '../api/designElements'
import type { DesignElementBrief } from '../api/types'

const props = defineProps<{ modelValue?: string | null; filter?: boolean; kind?: 'Design' | 'Asset' }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string | null): void }>()
const options = ref<DesignElementBrief[]>([])
const loading = ref(false)
const query = ref('')
const page = ref(1)
const more = ref(false)
let seq = 0
async function search(q = '', append = false) {
  const current = ++seq
  loading.value = true
  if (!append) { page.value = 1; query.value = q }
  try {
    const data = await listDesignElements({ q: query.value, page: page.value, archived: props.filter ? 'all' : 'false', kind: props.kind ?? (props.filter ? undefined : 'Design') })
    if (current !== seq) return
    options.value = append ? [...options.value, ...data.results] : data.results
    more.value = !!data.next
    if (props.modelValue && props.modelValue !== 'none' && !options.value.some(v => v.id === props.modelValue)) {
      const selected = await getDesignElement(props.modelValue)
      if (current === seq) options.value.unshift(selected)
    }
  } catch { if (current === seq) ElMessage.error('加载设计条目失败') }
  finally { if (current === seq) loading.value = false }
}
function loadMore() { page.value++; void search(query.value, true) }
watch(() => props.modelValue, () => { if (props.modelValue && !options.value.some(v => v.id === props.modelValue)) void search(query.value) })
watch(() => props.kind, () => { options.value = []; void search() })
onMounted(() => search())
</script>
<template>
  <el-select :model-value="modelValue || ''" filterable remote clearable :remote-method="search" :loading="loading" :placeholder="filter ? '设计或资产筛选' : kind === 'Asset' ? '上级资产（可空）' : '设计依据（可空）'" style="min-width: 200px" @update:model-value="emit('update:modelValue', $event || null)">
    <el-option v-if="filter" label="无设计或资产关联" value="none" />
    <el-option v-for="item in options" :key="item.id" :value="item.id" :label="item.title + (item.archived ? '（已归档）' : '')" :disabled="!filter && item.archived && item.id !== modelValue" />
    <template #footer><el-button v-if="more" link :loading="loading" @click="loadMore">加载更多</el-button></template>
  </el-select>
</template>
