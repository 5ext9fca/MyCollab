<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { QueryParams } from '../api/client'
import { listMissions } from '../api/missions'
import { filterLabels } from '../api/savedViews'
import type { Mission } from '../api/types'
import BulkMissionEditor from '../components/BulkMissionEditor.vue'
import MissionCard from '../components/MissionCard.vue'
import SavedViewsBar from '../components/SavedViewsBar.vue'
import MissionQuickFilters from '../components/MissionQuickFilters.vue'
import MissionQueryForm from '../components/MissionQueryForm.vue'
const router = useRouter(), route = useRoute()
const missions = ref<Mission[]>([]), total = ref(0), loading = ref(false), page = ref(1)
const pageSize = 20
const selectedIds = ref<string[]>([])
const resetKey = computed(() => JSON.stringify([route.query, page.value]))
const query = computed<QueryParams>(() => {
  const result: QueryParams = {}
  for (const key of Object.keys(filterLabels)) if (route.query[key]) result[key] = route.query[key] as string | string[]
  if (result.status === 'all') delete result.status
  else if (!('status' in route.query)) result.status = 'Open'
  if (!result.q && typeof route.query.search === 'string') result.q = route.query.search
  return result
})
let generation = 0
async function load() {
  const token = ++generation
  loading.value = true
  try { const data = await listMissions({ ...query.value, page: page.value, page_size: pageSize }); if (token === generation) { missions.value = data.results; total.value = data.count } }
  catch (e) { if (token === generation) ElMessage.error(e instanceof Error ? e.message : '加载失败') }
  finally { if (token === generation) loading.value = false }
}
function apply(value: QueryParams) {
  const next: Record<string, string | string[]> = { status: 'all' }
  for (const [key, item] of Object.entries(value)) if (item !== undefined && item !== null && item !== '') next[key] = Array.isArray(item) ? item.map(String) : String(item)
  if (typeof route.query.saved_view === 'string') next.saved_view = route.query.saved_view
  void router.push({ path: '/missions', query: next })
}
function remove(key: string) { const next = { ...query.value }; delete next[key]; if (key.startsWith('date_')) { delete next.date_from; delete next.date_to } apply(next) }
watch(() => route.query, () => { page.value = 1; void load() }, { immediate: true })
onUnmounted(() => { generation++ })
</script>
<template>
  <div class="page">
    <div class="page-header"><h2>任务广场</h2><el-button type="primary" @click="router.push({ name: 'mission-create' })">发布任务</el-button></div>
    <SavedViewsBar :query="query" target="List" @remove="remove" @opened="page = 1; selectedIds = []; load()" />
    <MissionQuickFilters :query="query" @apply="apply" />
    <MissionQueryForm :query="query" @apply="apply" />
    <BulkMissionEditor :missions="missions" v-model:selected-ids="selectedIds" :reset-key="resetKey" @changed="load" />
    <div v-loading="loading"><el-empty v-if="!loading && !missions.length" description="暂无任务" />
      <el-checkbox-group v-model="selectedIds" :max="50"><div v-for="mission in missions" :key="mission.id"><el-checkbox :value="mission.id" :label="mission.id">选择 {{ mission.title }}</el-checkbox><MissionCard :mission="mission" /></div></el-checkbox-group>
    </div>
    <el-pagination :total="total" :page-size="pageSize" :current-page="page" layout="prev, pager, next" @current-change="page = $event; load()" />
  </div>
</template>
