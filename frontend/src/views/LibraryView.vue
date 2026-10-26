<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { ApiException } from '../api/client'
import {
  deleteLibraryFile,
  formatFileSize,
  libraryMarkdown,
  listLibraryFiles,
  uploadLibraryFile,
} from '../api/library'
import type { LibraryFile } from '../api/types'

const files = ref<LibraryFile[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

async function load() {
  loading.value = true
  try {
    const data = await listLibraryFiles({ page: page.value, page_size: pageSize })
    files.value = data.results
    total.value = data.count
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function onPage(next: number) {
  page.value = next
  load()
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploading.value = true
  try {
    await uploadLibraryFile(file)
    page.value = 1
    await load()
    ElMessage.success('已上传')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '上传失败')
  } finally {
    uploading.value = false
  }
}

async function onCopy(file: LibraryFile) {
  try {
    await navigator.clipboard.writeText(libraryMarkdown(file))
    ElMessage.success('已复制 Markdown 引用')
  } catch {
    ElMessage.warning(`复制失败，请手动复制：${libraryMarkdown(file)}`)
  }
}

async function onDelete(file: LibraryFile) {
  try {
    await ElMessageBox.confirm(`确认删除「${file.original_name}」？`, '删除素材', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteLibraryFile(file.id)
    await load()
    ElMessage.success('已删除')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>我的素材库</h2>
      <div>
        <input ref="fileInput" type="file" style="display: none" @change="onFileChange" />
        <el-button type="primary" :loading="uploading" @click="fileInput?.click()">
          上传文件
        </el-button>
      </div>
    </div>

    <p class="meta">
      文件按用户隔离存放。Markdown 中只能引用自己的素材（或外链 URL），其他成员的素材不会被引用。
    </p>

    <el-table v-loading="loading" :data="files">
      <el-table-column label="预览" width="80">
        <template #default="{ row }">
          <el-image
            v-if="row.content_type.startsWith('image/')"
            :src="row.url"
            fit="cover"
            style="width: 40px; height: 40px; border-radius: 4px"
          />
          <span v-else class="meta">文件</span>
        </template>
      </el-table-column>
      <el-table-column label="文件名" min-width="200">
        <template #default="{ row }">
          <a class="app-link app-link--action" :href="row.url" target="_blank" rel="noopener">{{ row.original_name }}</a>
        </template>
      </el-table-column>
      <el-table-column label="类型" prop="content_type" width="180" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="上传时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button class="app-link app-link--action" link type="primary" @click="onCopy(row)">复制 Markdown</el-button>
          <el-button class="app-link app-link--action" link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      background
      layout="prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="onPage"
    />
  </div>
</template>
