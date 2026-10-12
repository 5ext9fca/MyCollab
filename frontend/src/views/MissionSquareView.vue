<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import { listMilestones } from '../api/milestones'
import { listMissions, listTags } from '../api/missions'
import type { Milestone, Mission, MissionPriority, MissionStatus, MissionType } from '../api/types'
import { PRIORITY_OPTIONS, TYPE_OPTIONS } from '../missionMeta'
import MissionCard from '../components/MissionCard.vue'

const router = useRouter()

const missions = ref<Mission[]>([])
const total = ref(0)
const loading = ref(false)
const tagOptions = ref<string[]>([])
const milestoneOptions = ref<Milestone[]>([])
const page = ref(1)
const pageSize = 10

const filters = reactive<{
  search: string
  tags: string[]
  status: MissionStatus | ''
  type: MissionType | ''
  priority: MissionPriority | ''
  milestone: string
  blocked: '' | 'true' | 'false'
  ordering: '' | 'priority' | '-priority'
}>({
  search: '',
  tags: [],
  status: 'Open',
  type: '',
  priority: '',
  milestone: '',
  blocked: '',
  ordering: '',
})

const statusOptions: { label: string; value: MissionStatus | '' }[] = [
  { label: '待认领', value: 'Open' },
  { label: '进行中', value: 'InProgress' },
  { label: '待验收', value: 'Submitted' },
  { label: '已完成', value: 'Done' },
  { label: '全部', value: '' },
]

const blockedOptions = [
  { label: '全部（含受阻）', value: '' },
  { label: '仅受阻', value: 'true' },
  { label: '不受阻', value: 'false' },
]

const orderingOptions = [
  { label: '默认排序', value: '' },
  { label: '优先级高在前', value: 'priority' },
  { label: '优先级低在前', value: '-priority' },
]

async function load() {
  loading.value = true
  try {
    const data = await listMissions({
      status: filters.status || undefined,
      // Repeated ``tag`` params; the API ANDs them (must carry every tag).
      tag: filters.tags.length ? filters.tags : undefined,
      search: filters.search || undefined,
      type: filters.type || undefined,
      priority: filters.priority || undefined,
      milestone: filters.milestone || undefined,
      blocked: filters.blocked === '' ? undefined : filters.blocked,
      ordering: filters.ordering || undefined,
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
  const [tags, milestones] = await Promise.allSettled([listTags(), listMilestones({ page_size: 100 })])
  if (tags.status === 'fulfilled') tagOptions.value = tags.value.map((tag) => tag.name)
  if (milestones.status === 'fulfilled') milestoneOptions.value = milestones.value.results
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
        style="width: 220px"
        clearable
        @keyup.enter="onFilter"
        @clear="onFilter"
      />
      <el-select v-model="filters.status" style="width: 120px" @change="onFilter">
        <el-option v-for="item in statusOptions" :key="item.label" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.type" placeholder="类型" clearable style="width: 130px" @change="onFilter">
        <el-option v-for="item in TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.priority" placeholder="优先级" clearable style="width: 120px" @change="onFilter">
        <el-option v-for="item in PRIORITY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select
        v-model="filters.milestone"
        placeholder="里程碑"
        clearable
        filterable
        style="width: 180px"
        @change="onFilter"
      >
        <el-option v-for="item in milestoneOptions" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-select v-model="filters.blocked" style="width: 150px" @change="onFilter">
        <el-option v-for="item in blockedOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.ordering" style="width: 150px" @change="onFilter">
        <el-option v-for="item in orderingOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select
        v-model="filters.tags"
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="标签（需同时包含）"
        style="width: 200px"
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
