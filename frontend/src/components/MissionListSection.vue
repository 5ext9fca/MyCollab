<script setup lang="ts">
import ActionCardList from './ActionCardList.vue'
import CardListSelection from './CardListSelection.vue'
import { useCardList } from '../composables/useCardList'
import { ref } from 'vue'
import type { QueryParams } from '../api/client'
import { listMissions } from '../api/missions'
import MissionCard from './MissionCard.vue'
import MissionQuickFilters from './MissionQuickFilters.vue'
import BulkMissionEditor from './BulkMissionEditor.vue'
const props = defineProps<{ title: string; query: Record<string, string> }>()
const filters = ref<QueryParams>({}), selectedIds = ref<string[]>([]), actionBusy = ref(false)
const { items: missions, total, loading, page, pageSize, resetKey, reload: load } = useCardList(() => ({ ...filters.value, ...props.query }), listMissions)
function apply(value: QueryParams) { filters.value = value }
</script>
<template>
  <div class="page">
    <div class="page-header"><h2>{{ title }}</h2></div>
    <ActionCardList :busy="actionBusy" :items="missions" :total="total" :loading="loading" v-model:page="page" v-model:page-size="pageSize" v-model:selected-ids="selectedIds" :reset-key="resetKey" empty-text="暂无任务">
      <template #filters><MissionQuickFilters :query="filters" @apply="apply" /></template>
      <template #actions><BulkMissionEditor @update:busy="actionBusy = $event" :missions="missions" v-model:selected-ids="selectedIds" :reset-key="resetKey" @changed="load" /></template>
      <template #item="{ item: mission }"><MissionCard :mission="mission">
        <template #selection><CardListSelection :id="mission.id" :label="`选择 ${mission.title}`" /></template>
      </MissionCard></template>
    </ActionCardList>
  </div>
</template>
