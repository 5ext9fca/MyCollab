<script setup lang="ts">
import CardListSort from './CardListSort.vue'
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { QueryParams, QueryParamValue } from '../api/client'
import { listMilestones } from '../api/milestones'
import { listTags } from '../api/missions'
import { STATUS_OPTIONS, TYPE_OPTIONS, PRIORITY_OPTIONS } from '../missionMeta'
import DesignElementSelect from './DesignElementSelect.vue'
const props = defineProps<{ query: QueryParams }>()
const emit = defineEmits<{ apply: [query: QueryParams] }>()
const search = ref(''), tags = ref<string[]>([]), milestones = ref<{ id: string; name: string }[]>([])
watch(() => props.query.q, value => { search.value = String(value ?? '') }, { immediate: true })
function set(key: string, value: QueryParamValue) { const query = { ...props.query }; if (value === '' || value === null || value === undefined) delete query[key]; else query[key] = value; emit('apply', query) }
onMounted(async () => {
  const data = await Promise.allSettled([listTags(), listMilestones({ page_size: 100 })])
  if (data[0].status === 'fulfilled') tags.value = data[0].value.map(tag => tag.name)
  if (data[1].status === 'fulfilled') milestones.value = data[1].value.results
  if (data.some(result => result.status === 'rejected')) ElMessage.warning('部分筛选选项加载失败，仍可使用全部筛选条件')
})
</script>
<template>
  <div class="toolbar">
    <DesignElementSelect :model-value="String(query.design_element || '')" filter @update:model-value="set('design_element', $event)" />
    <el-input v-model="search" placeholder="搜索标题或内容" clearable style="width: 220px" @keyup.enter="set('q', search)" @clear="set('q', '')" />
    <el-select :model-value="String(query.status || '')" placeholder="全部状态" clearable style="width: 130px" @update:model-value="set('status', $event)"><el-option v-for="item in STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select>
    <el-select :model-value="String(query.type || '')" placeholder="类型" clearable style="width: 140px" @update:model-value="set('type', $event)"><el-option v-for="item in TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select>
    <el-select :model-value="String(query.priority || '')" placeholder="优先级" clearable style="width: 140px" @update:model-value="set('priority', $event)"><el-option v-for="item in PRIORITY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select>
    <el-select :model-value="String(query.milestone || '')" placeholder="里程碑" clearable filterable style="width: 180px" @update:model-value="set('milestone', $event)"><el-option label="未归属里程碑" value="none" /><el-option v-for="item in milestones" :key="item.id" :label="item.name" :value="item.id" /></el-select>
    <el-select :model-value="Array.isArray(query.tag) ? query.tag : query.tag ? String(query.tag).split(',') : []" multiple collapse-tags clearable filterable placeholder="标签（需同时包含）" style="width: 200px" @update:model-value="set('tag', $event)"><el-option v-for="tag in tags" :key="tag" :label="tag" :value="tag" /></el-select>
    <el-select :model-value="String(query.blocked || '')" placeholder="受阻状态" clearable style="width: 140px" @update:model-value="set('blocked', $event)"><el-option label="仅受阻" value="true" /><el-option label="不受阻" value="false" /></el-select>
    <CardListSort :model-value="String(query.ordering || '')" clearable @update:model-value="set('ordering', $event)" :options="[{ label: '最新发布', value: '-created_at' }, { label: '最早发布', value: 'created_at' }, { label: '最近更新', value: '-updated_at' }, { label: '标题升序', value: 'title' }, { label: '标题降序', value: '-title' }, { label: '优先级高在前', value: 'priority' }, { label: '优先级低在前', value: '-priority' }]" />
    <el-button @click="set('q', search)">查询</el-button>
  </div>
</template>
