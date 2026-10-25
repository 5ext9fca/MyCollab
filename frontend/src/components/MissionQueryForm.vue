<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { QueryParams } from '../api/client'
import { filterLabels } from '../api/savedViews'
const props = defineProps<{ query: QueryParams }>()
const emit = defineEmits<{ apply: [query: QueryParams] }>()
const fields = reactive<Record<string, string>>({})
watch(() => props.query, query => { for (const key of Object.keys(filterLabels)) fields[key] = Array.isArray(query[key]) ? query[key].join(',') : String(query[key] ?? '') }, { immediate: true, deep: true })
const options: Record<string, string[]> = { status: ['Open', 'InProgress', 'Submitted', 'Done', 'Cancelled'], type: ['Feature', 'Task', 'Bug'], priority: ['P0', 'P1', 'P2', 'P3'], blocked: ['true', 'false'], revalidation: ['true', 'false'], ordering: ['created_at', '-created_at', 'updated_at', '-updated_at', 'title', '-title', 'status', '-status', 'priority', '-priority', 'type', '-type'] }
const hints: Record<string, string> = { creator: '成员 ID / me / none', assignee: '成员 ID / me / none', reviewer: '成员 ID / me / none', parent: '任务 ID / root', milestone: '里程碑 ID / none', design_element: '设计条目 ID / none', production_batch: '批次 ID / none', tag: '以逗号分隔，需同时包含' }
function apply() { const query: QueryParams = {}; for (const [key, value] of Object.entries(fields)) if (typeof value === 'string' && value.trim()) query[key] = key === 'tag' ? value.split(',').map(t => t.trim()).filter(Boolean) : value.trim(); emit('apply', query) }
</script>
<template>
  <el-collapse><el-collapse-item title="编辑全部筛选条件" name="filters"><el-form label-width="160px" class="query-grid">
    <el-form-item v-for="(label, key) in filterLabels" :key="key" :label="label">
      <el-select v-if="options[key]" v-model="fields[key]" clearable><el-option v-for="value in options[key]" :key="value" :label="value" :value="value" /></el-select>
      <el-date-picker v-else-if="key === 'date_from' || key === 'date_to'" v-model="fields[key]" value-format="YYYY-MM-DD" clearable />
      <el-input v-else v-model="fields[key]" :placeholder="hints[key] || label" clearable />
    </el-form-item>
  </el-form><el-button type="primary" @click="apply">应用筛选</el-button></el-collapse-item></el-collapse>
</template>
<style scoped>.query-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 0 18px; }</style>
