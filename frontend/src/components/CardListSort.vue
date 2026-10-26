<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; options: { label: string; value: string }[]; label?: string; clearable?: boolean }>(), { label: '排序', clearable: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <el-select :model-value="modelValue" :aria-label="label" :placeholder="label" :clearable="clearable" style="width: 170px" @update:model-value="emit('update:modelValue', $event)">
    <el-option v-for="option in options" :key="option.value" :label="option.label" :value="option.value" />
  </el-select>
</template>
