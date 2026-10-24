<script setup lang="ts">
import type { ProductionStep } from '../api/types'
import { PRIORITY_OPTIONS, TYPE_OPTIONS } from '../missionMeta'
import MarkdownEditor from './MarkdownEditor.vue'
const props = defineProps<{ modelValue: ProductionStep[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', steps: ProductionStep[]): void }>()
function add() {
  let n = props.modelValue.length + 1
  while (props.modelValue.some(step => step.key === `step_${n}`)) n++
  emit('update:modelValue', [...props.modelValue, { key: `step_${n}`, title: '', content: '', acceptance_criteria: '', type: 'Task', priority: 'P2', tags: [], prerequisite_keys: [] }])
}
function remove(index: number) {
  const key = props.modelValue[index]!.key
  emit('update:modelValue', props.modelValue.filter((_, i) => i !== index).map(step => ({ ...step, prerequisite_keys: step.prerequisite_keys.filter(k => k !== key) })))
}
function move(index: number, offset: number) {
  const steps = [...props.modelValue]
  const target = index + offset
  if (target < 0 || target >= steps.length) return
  ;[steps[index], steps[target]] = [steps[target]!, steps[index]!]
  emit('update:modelValue', steps)
}
</script>
<template>
  <p class="meta">步骤顺序只影响展示。通过“前置步骤”声明等待关系；未关联的步骤可并行。删除步骤会同时移除对它的模板依赖。</p>
  <el-card v-for="(step, index) in modelValue" :key="index" class="step-card" shadow="never">
    <template #header><div class="toolbar"><strong>步骤 {{ index + 1 }}</strong><el-button :disabled="index === 0" @click="move(index, -1)">上移</el-button><el-button :disabled="index === modelValue.length - 1" @click="move(index, 1)">下移</el-button><el-button type="danger" :disabled="modelValue.length === 1" @click="remove(index)">删除步骤</el-button></div></template>
    <el-form-item label="步骤标识（字母、数字或下划线）"><el-input v-model="step.key" maxlength="50" /></el-form-item>
    <el-form-item label="步骤标题"><el-input v-model="step.title" maxlength="200" /></el-form-item>
    <el-form-item label="前置步骤"><el-select v-model="step.prerequisite_keys" multiple filterable placeholder="无前置，可并行"><el-option v-for="other in modelValue.filter(s => s !== step)" :key="other.key" :value="other.key" :label="`${other.title || '未命名'}（${other.key}）`" /></el-select></el-form-item>
    <el-form-item label="类型"><el-select v-model="step.type"><el-option v-for="o in TYPE_OPTIONS" :key="o.value" :value="o.value" :label="o.label" /></el-select></el-form-item>
    <el-form-item label="优先级"><el-select v-model="step.priority"><el-option v-for="o in PRIORITY_OPTIONS" :key="o.value" :value="o.value" :label="o.label" /></el-select></el-form-item>
    <el-form-item label="标签"><el-select v-model="step.tags" multiple filterable allow-create default-first-option><el-option v-for="tag in step.tags" :key="tag" :value="tag" :label="tag" /></el-select></el-form-item>
    <el-form-item label="背景与目标"><MarkdownEditor v-model="step.content" :allow-library="false" /></el-form-item>
    <el-form-item label="验收标准"><MarkdownEditor v-model="step.acceptance_criteria" :allow-library="false" /></el-form-item>
  </el-card>
  <el-button :disabled="modelValue.length >= 30" @click="add">添加步骤（{{ modelValue.length }}/30）</el-button>
</template>
<style scoped>.step-card { margin-bottom: 16px; } .el-select { width: 100%; }</style>
