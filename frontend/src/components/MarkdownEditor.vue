<script setup lang="ts">
import { nextTick, ref } from 'vue'

import LibraryPicker from './LibraryPicker.vue'

const props = withDefaults(
  defineProps<{ modelValue: string; rows?: number; placeholder?: string; allowLibrary?: boolean }>(),
  { rows: 5, placeholder: '', allowLibrary: true },
)
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const wrapper = ref<HTMLElement | null>(null)
const pickerVisible = ref(false)

function textarea(): HTMLTextAreaElement | null {
  return wrapper.value?.querySelector('textarea') ?? null
}

async function insert(text: string) {
  const element = textarea()
  const current = props.modelValue ?? ''
  if (!element) {
    emit('update:modelValue', current ? `${current}\n${text}` : text)
    return
  }
  const start = element.selectionStart ?? current.length
  const end = element.selectionEnd ?? start
  emit('update:modelValue', `${current.slice(0, start)}${text}${current.slice(end)}`)
  await nextTick()
  element.focus()
  const caret = start + text.length
  element.setSelectionRange(caret, caret)
}

async function onSelect(markdown: string) {
  pickerVisible.value = false
  await insert(markdown)
}

function onInput(value: string) {
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="markdown-editor">
    <div ref="wrapper">
      <el-input
        type="textarea"
        :rows="rows"
        :placeholder="placeholder"
        :model-value="modelValue"
        @update:model-value="onInput"
      />
    </div>
    <div class="markdown-editor__actions">
      <el-button v-if="allowLibrary" size="small" @click="pickerVisible = true">插入素材</el-button>
      <span class="markdown-editor__hint">{{ allowLibrary ? '只能引用自己素材库内的文件或外链 URL' : '模板只能引用 http(s) 外链，生成后可补充自己的素材' }}</span>
    </div>
    <LibraryPicker v-if="allowLibrary" v-model="pickerVisible" @select="onSelect" />
  </div>
</template>

<style scoped>
.markdown-editor__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.markdown-editor__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
