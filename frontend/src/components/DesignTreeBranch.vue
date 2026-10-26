<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listDesignElements } from '../api/designElements'
import type { DesignElement } from '../api/types'
const props = defineProps<{ parent?: string; archived: string; query?: string; kind?: string }>()
const items = ref<DesignElement[]>([])
const expanded = ref(new Set<string>())
const page = ref(0)
const more = ref(true)
const loading = ref(false)
async function load() {
  loading.value = true
  try {
    const result = await listDesignElements({ parent: props.parent ?? (props.query || props.archived === 'true' ? undefined : 'root'), archived: props.archived, q: props.query, kind: props.kind || undefined, page: page.value + 1 })
    items.value.push(...result.results); page.value++; more.value = !!result.next
  } catch { ElMessage.error('加载设计树失败') }
  finally { loading.value = false }
}
function toggle(id: string) { if (expanded.value.has(id)) expanded.value.delete(id); else expanded.value.add(id) }
onMounted(load)
</script>
<template>
  <ul class="design-tree">
    <li v-for="item in items" :key="item.id">
      <el-card class="design-item-card" shadow="never">
      <div class="tree-row">
        <el-button v-if="item.has_children && !query" text :aria-expanded="expanded.has(item.id)" :aria-label="'展开或折叠' + item.title" @click="toggle(item.id)">{{ expanded.has(item.id) ? '−' : '+' }}</el-button>
        <router-link class="app-link app-link--title" :to="{ name: 'design', params: { id: item.id } }">{{ item.title }}</router-link>
        <small>{{ item.kind === 'Asset' ? '资产' : '设计' }}{{ item.archived ? ' · 已归档' : '' }}</small>
      </div>
      <DesignTreeBranch v-if="expanded.has(item.id)" class="design-children" :parent="item.id" :archived="archived" :kind="kind" />
      </el-card>
    </li>
    <li v-if="!items.length && !loading" class="meta">暂无条目</li>
    <li v-if="more"><el-button link :loading="loading" @click="load">{{ page ? '加载更多' : '加载条目' }}</el-button></li>
  </ul>
</template>
<style scoped>
.design-tree { list-style: none; padding: 0; margin: 0; }
.design-children { margin-top: 12px; }
.design-children :deep(.el-card__body) { padding: 12px; }
.design-children > li:last-child > .design-item-card { margin-bottom: 0; }
.design-item-card { margin-bottom: 16px; }
.tree-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
small { color: var(--el-text-color-secondary); }
</style>
