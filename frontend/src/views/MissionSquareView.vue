<script setup lang="ts">
import ActionCardList from '../components/ActionCardList.vue'
import CardListSelection from '../components/CardListSelection.vue'
import { useCardList } from '../composables/useCardList'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { QueryParams } from '../api/client'
import { listMissions } from '../api/missions'
import { filterLabels } from '../api/savedViews'
import BulkMissionEditor from '../components/BulkMissionEditor.vue'
import MissionCard from '../components/MissionCard.vue'
import SavedViewsBar from '../components/SavedViewsBar.vue'
import MissionQuickFilters from '../components/MissionQuickFilters.vue'
import MissionQueryForm from '../components/MissionQueryForm.vue'
const router = useRouter(), route = useRoute()
const selectedIds = ref<string[]>([]), actionBusy = ref(false)
const query = computed<QueryParams>(() => {
  const result: QueryParams = {}
  for (const key of Object.keys(filterLabels)) if (route.query[key]) result[key] = route.query[key] as string | string[]
  if (result.status === 'all') delete result.status
  else if (!('status' in route.query)) result.status = 'Open'
  if (!result.q && typeof route.query.search === 'string') result.q = route.query.search
  return result
})
const { items: missions, total, loading, page, pageSize, resetKey, reload: load } = useCardList(() => query.value, listMissions)
function apply(value: QueryParams) {
  const next: Record<string, string | string[]> = { status: 'all' }
  for (const [key, item] of Object.entries(value)) if (item !== undefined && item !== null && item !== '') next[key] = Array.isArray(item) ? item.map(String) : String(item)
  if (typeof route.query.saved_view === 'string') next.saved_view = route.query.saved_view
  void router.push({ path: '/missions', query: next })
}
function remove(key: string) { const next = { ...query.value }; delete next[key]; if (key.startsWith('date_')) { delete next.date_from; delete next.date_to } apply(next) }
</script>
<template>
  <div class="page">
    <div class="page-header"><h2>任务广场</h2><el-button type="primary" @click="router.push({ name: 'mission-create' })">发布任务</el-button></div>
    <SavedViewsBar :query="query" target="List" @remove="remove" @opened="page = 1; selectedIds = []; load()" />
    <MissionQueryForm :query="query" @apply="apply" />
    <ActionCardList :busy="actionBusy" :items="missions" :total="total" :loading="loading" v-model:page="page" v-model:page-size="pageSize" v-model:selected-ids="selectedIds" :reset-key="resetKey" empty-text="暂无任务">
      <template #filters><MissionQuickFilters :query="query" @apply="apply" /></template>
      <template #actions><BulkMissionEditor @update:busy="actionBusy = $event" :missions="missions" v-model:selected-ids="selectedIds" :reset-key="resetKey" @changed="load" /></template>
      <template #item="{ item: mission }"><MissionCard :mission="mission">
        <template #selection><CardListSelection :id="mission.id" :label="`选择 ${mission.title}`" /></template>
      </MissionCard></template>
    </ActionCardList>
  </div>
</template>
