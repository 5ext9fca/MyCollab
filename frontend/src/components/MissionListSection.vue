<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import { listMissions } from '../api/missions'
import type { Mission } from '../api/types'
import MissionCard from './MissionCard.vue'

const props = defineProps<{ title: string; query: Record<string, string> }>()

const missions = ref<Mission[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 10

async function load() {
  loading.value = true
  try {
    const data = await listMissions({ ...props.query, page: page.value, page_size: pageSize })
    missions.value = data.results
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

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ title }}</h2>
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
