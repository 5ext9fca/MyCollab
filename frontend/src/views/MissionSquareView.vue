<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import { listMissions, listTags } from '../api/missions'
import type { Mission, MissionStatus } from '../api/types'
import MissionCard from '../components/MissionCard.vue'

const router = useRouter()

const missions = ref<Mission[]>([])
const total = ref(0)
const loading = ref(false)
const tagOptions = ref<string[]>([])
const page = ref(1)
const pageSize = 10

const filters = reactive<{ search: string; tags: string[]; status: MissionStatus | '' }>({
  search: '',
  tags: [],
  status: 'Open',
})

const statusOptions: { label: string; value: MissionStatus | '' }[] = [
  { label: '待认领', value: 'Open' },
  { label: '进行中', value: 'InProgress' },
  { label: '待验收', value: 'Submitted' },
  { label: '已完成', value: 'Done' },
  { label: '全部', value: '' },
]

async function load() {
  loading.value = true
  try {
    const data = await listMissions({
      status: filters.status || undefined,
      // Repeated ``tag`` params; the API ANDs them (must carry every tag).
      tag: filters.tags.length ? filters.tags : undefined,
      search: filters.search || undefined,
      page: page.value,
      page_size: pageSize,
    })
    missions.value = data.results
    total.value = data.count
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function onFilter() {
  page.value = 1
  load()
}

function onPage(next: number) {
  page.value = next
  load()
}

onMounted(async () => {
  try {
    tagOptions.value = (await listTags()).map((tag) => tag.name)
  } catch {
    /* tags are optional */
  }
  await load()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>任务广场</h2>
      <el-button type="primary" @click="router.push({ name: 'mission-create' })">
        发布任务
      </el-button>
    </div>

    <div class="toolbar">
      <el-input
        v-model="filters.search"
        placeholder="搜索标题或内容"
        style="width: 240px"
        clearable
        @keyup.enter="onFilter"
        @clear="onFilter"
      />
      <el-select v-model="filters.status" style="width: 140px" @change="onFilter">
        <el-option v-for="item in statusOptions" :key="item.label" :label="item.label" :value="item.value" />
      </el-select>
      <el-select
        v-model="filters.tags"
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="标签（需同时包含）"
        style="width: 220px"
        clearable
        filterable
        @change="onFilter"
      >
        <el-option v-for="name in tagOptions" :key="name" :label="name" :value="name" />
      </el-select>
      <el-button @click="onFilter">查询</el-button>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!loading && !missions.length" description="暂无任务" />
      <MissionCard v-for="mission in missions" :key="mission.id" :mission="mission" />
    </div>

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
