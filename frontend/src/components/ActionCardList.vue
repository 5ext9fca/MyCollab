<script setup lang="ts" generic="T extends { id: string }">
import { computed, watch } from 'vue'
import CardList from './CardList.vue'
const props = withDefaults(defineProps<{ items: T[]; total: number; loading: boolean; page: number; pageSize: number; resetKey: string; selectedIds: string[]; busy?: boolean; maxSelection?: number; emptyText?: string }>(), { busy: false, maxSelection: 50 })
const emit = defineEmits<{ 'update:page': [value: number]; 'update:pageSize': [value: number]; 'update:selectedIds': [value: string[]] }>()
const selected = computed(() => props.items.filter(item => props.selectedIds.includes(item.id)))
function select(ids: string[]) {
  if (props.busy || props.loading) return
  emit('update:selectedIds', ids.filter(id => props.items.some(item => item.id === id)).slice(0, props.maxSelection))
}
watch([() => props.items, () => props.loading], () => {
  if (!props.loading) {
    const ids = selected.value.map(item => item.id)
    if (ids.length !== props.selectedIds.length) emit('update:selectedIds', ids)
  }
})
watch(() => props.resetKey, () => emit('update:selectedIds', []))
</script>
<template>
  <CardList :items="items" :total="total" :loading="loading" :page="page" :page-size="pageSize" :empty-text="emptyText" @update:page="emit('update:page', $event)" @update:page-size="emit('update:pageSize', $event)">
    <template v-if="$slots.filters" #filters><slot name="filters" /></template>
    <template #before-items>
      <el-card class="section-card" shadow="never"><div class="toolbar toolbar--flush">
        <el-checkbox :model-value="items.length > 0 && selected.length === items.length" :indeterminate="selected.length > 0 && selected.length < items.length" :disabled="busy || loading || !items.length || items.length > maxSelection" @change="select($event ? items.map(item => item.id) : [])">本页全选</el-checkbox>
        <el-card class="selection-summary" shadow="never" :body-style="{ padding: '8px 12px' }">
          <div class="selection-summary__content" role="status" aria-live="polite">
            <span class="meta">本页已选</span>
            <strong>{{ selected.length }} / {{ maxSelection }}</strong>
          </div>
        </el-card>
        <slot name="actions" :selected="selected" :selected-ids="selected.map(item => item.id)" :disabled="busy || loading || !selected.length" />
      </div></el-card>
    </template>
    <template #items>
      <el-checkbox-group :model-value="selectedIds" :max="maxSelection" :disabled="busy || loading" @update:model-value="select($event as string[])">
        <template v-for="item in items" :key="item.id"><slot name="item" :item="item" /></template>
      </el-checkbox-group>
    </template>
  </CardList>
</template>

<style scoped>
.selection-summary__content { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.selection-summary strong { font-variant-numeric: tabular-nums; }
</style>
