<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import {
  deleteLibraryFile,
  formatFileSize,
  libraryMarkdown,
  listLibraryFiles,
  uploadLibraryFile,
} from '../api/library'
import type { LibraryFile } from '../api/types'

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ select: [string] }>()

const files = ref<LibraryFile[]>([])
const loading = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

async function load() {
  loading.value = true
  try {
    const data = await listLibraryFiles({ page_size: 50 })
    files.value = data.results
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载素材失败')
  } finally {
    loading.value = false
  }
}

watch(visible, (open) => {
  if (open) load()
})

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploading.value = true
  try {
    await uploadLibraryFile(file)
    await load()
    ElMessage.success('已上传到素材库')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '上传失败')
  } finally {
    uploading.value = false
  }
}

function onInsert(file: LibraryFile) {
  emit('select', libraryMarkdown(file))
}

async function onDelete(file: LibraryFile) {
  try {
    await deleteLibraryFile(file.id)
    await load()
    ElMessage.success('已删除')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '删除失败')
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="素材库" width="640px">
    <div class="picker__toolbar">
      <input ref="fileInput" type="file" style="display: none" @change="onFileChange" />
      <el-button type="primary" :loading="uploading" @click="fileInput?.click()">
        上传文件
      </el-button>
      <span class="meta">只可使用自己的素材或外链；支持图片与常见文档</span>
    </div>

    <div v-loading="loading" class="picker__list">
      <el-empty v-if="!loading && !files.length" description="还没有素材" :image-size="60" />
      <div v-for="file in files" :key="file.id" class="picker__row">
        <el-image
          v-if="file.content_type.startsWith('image/')"
          :src="file.url"
          fit="cover"
          class="picker__thumb"
        />
        <span v-else class="picker__icon">文件</span>
        <div class="picker__info">
          <div class="picker__name">{{ file.original_name }}</div>
          <div class="meta">
            {{ formatFileSize(file.size) }} · {{ new Date(file.created_at).toLocaleString() }}
          </div>
        </div>
        <el-button size="small" type="primary" @click="onInsert(file)">插入</el-button>
        <el-button class="app-link app-link--action" size="small" type="danger" link @click="onDelete(file)">删除</el-button>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.picker__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.picker__list {
  min-height: 120px;
  max-height: 50vh;
  overflow-y: auto;
}
.picker__row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid var(--el-border-color);
}
.picker__row:first-child {
  border-top: none;
}
.picker__thumb {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  flex: none;
}
.picker__icon {
  width: 40px;
  height: 40px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.picker__info {
  flex: 1;
  min-width: 0;
}
.picker__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
