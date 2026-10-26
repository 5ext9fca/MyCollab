<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getDesignElement, listDesignElements } from '../api/designElements'
import type { DesignElementBrief } from '../api/types'

const props = withDefaults(defineProps<{ modelValue?: string[]; kind?: 'Design' | 'Asset'; excludeId?: string; label?: string }>(), { kind: 'Asset', label: '相关资产' })
const emit = defineEmits<{ (e: 'update:modelValue', value: string[]): void }>()
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
    const data = await listDesignElements({ kind: props.kind, archived: 'false', q: query.value, page: page.value })
    const values = append ? [...options.value, ...data.results] : data.results
    const missing = (props.modelValue ?? []).filter(id => !values.some(item => item.id === id))
    const selected = await Promise.all(missing.map(id => getDesignElement(id)))
    if (current !== seq) return
    options.value = [...selected, ...values].filter(item => item.id !== props.excludeId && item.kind === props.kind)
    more.value = !!data.next
  } catch { if (current === seq) ElMessage.error('加载条目失败') }
  finally { if (current === seq) loading.value = false }
}
function loadMore() { page.value++; void search(query.value, true) }
watch(() => props.modelValue, () => { if (props.modelValue?.some(id => !options.value.some(item => item.id === id))) void search(query.value) })
watch(() => props.kind, () => { options.value = []; void search() })
onMounted(() => search())
</script>
<template>
  <el-select :model-value="modelValue ?? []" multiple filterable remote clearable :remote-method="search" :loading="loading" :placeholder="`选择${label}（可多选）`" :aria-label="label" style="width: 100%" @update:model-value="emit('update:modelValue', $event)">
    <el-option v-for="item in options" :key="item.id" :value="item.id" :label="item.title + (item.archived ? '（已归档）' : '')" :disabled="item.archived && !modelValue?.includes(item.id)" />
    <template #footer><el-button class="app-link app-link--action" v-if="more" link :loading="loading" @click="loadMore">加载更多</el-button></template>
  </el-select>
</template>
