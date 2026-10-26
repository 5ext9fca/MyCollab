<script setup lang="ts">
import ElementMultiSelect from './ElementMultiSelect.vue'
defineProps<{ modelValue?: string[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string[]): void }>()
</script>
<template>
  <ElementMultiSelect :model-value="modelValue" kind="Asset" label="相关资产" @update:model-value="emit('update:modelValue', $event)" />
</template>
