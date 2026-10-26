<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { QueryParams } from '../api/client'
import { listMissions } from '../api/missions'
import type { Mission } from '../api/types'
import MissionCard from './MissionCard.vue'
import MissionQuickFilters from './MissionQuickFilters.vue'
import BulkMissionEditor from './BulkMissionEditor.vue'
const props = defineProps<{ title: string; query: Record<string, string> }>()
const missions = ref<Mission[]>([]), total = ref(0), loading = ref(false)
const page = ref(1), pageSize = ref(20), filters = ref<QueryParams>({}), selectedIds = ref<string[]>([])
const resetKey = computed(() => JSON.stringify([props.query, filters.value, page.value, pageSize.value]))
let generation = 0
async function load() {
  const token = ++generation
  loading.value = true
  selectedIds.value = []
  missions.value = []
  try {
    const data = await listMissions({ ...filters.value, ...props.query, page: page.value, page_size: pageSize.value })
    if (token === generation) { missions.value = data.results; total.value = data.count }
  } catch (error) { if (token === generation) ElMessage.error(error instanceof Error ? error.message : '加载失败') }
  finally { if (token === generation) loading.value = false }
}
function apply(value: QueryParams) { filters.value = value; page.value = 1 }
watch(() => props.query, () => { page.value = 1 }, { deep: true })
watch(resetKey, load, { immediate: true })
onUnmounted(() => { generation++ })
</script>
<template>
  <div class="page">
    <div class="page-header"><h2>{{ title }}</h2></div>
    <el-card class="section-card" shadow="never"><MissionQuickFilters :query="filters" @apply="apply" /></el-card>
    <BulkMissionEditor :missions="missions" v-model:selected-ids="selectedIds" :reset-key="resetKey" @changed="load" />
    <div v-loading="loading">
      <el-empty v-if="!loading && !missions.length" description="暂无任务" />
      <el-checkbox-group v-model="selectedIds" :max="50">
        <MissionCard v-for="mission in missions" :key="mission.id" :mission="mission">
          <template #selection><el-checkbox :value="mission.id" :aria-label="`选择 ${mission.title}`" /></template>
        </MissionCard>
      </el-checkbox-group>
    </div>
    <el-pagination class="list-pagination" :total="total" :page-size="pageSize" :current-page="page" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @current-change="page = $event" @size-change="pageSize = $event; page = 1" />
  </div>
</template>
