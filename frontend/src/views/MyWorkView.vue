<script setup lang="ts">
import ActionCardList from '../components/ActionCardList.vue'
import CardListSelection from '../components/CardListSelection.vue'
import { useCardList } from '../composables/useCardList'
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { workSummary, workMissions, notifyChanged, type WorkCategory, type WorkSummary } from '../api/notifications'
import MissionQuickFilters from '../components/MissionQuickFilters.vue'
import type { QueryParams } from '../api/client'
import BulkMissionEditor from '../components/BulkMissionEditor.vue'
import MissionCard from '../components/MissionCard.vue'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
const labels: Record<WorkCategory, string> = { review: '待我验收', returned: '被退回', due_soon: '即将到期', overdue: '已逾期', unblocked: '依赖已解除', revalidation: '需要复核' }
const filters = ref<QueryParams>({})
function apply(value: QueryParams) { filters.value = value }
const category = ref<WorkCategory>('review')
const summary = ref<WorkSummary | null>(null)
const fetchedAt = ref(''), selected = ref<string | null>(null), selectedIds = ref<string[]>([]), actionBusy = ref(false)
const { items: missions, total, loading, page, pageSize, resetKey, reload: load } = useCardList(() => ({ ...filters.value, category: category.value }), params => workMissions(category.value, Number(params.page), params))
let summaryGeneration = 0
async function refreshSummary() {
  const token = ++summaryGeneration
  try {
    const data = await workSummary()
    if (token !== summaryGeneration) return
    const crossedDay = summary.value && summary.value.today !== data.today
    summary.value = data; fetchedAt.value = new Date().toLocaleTimeString()
    if (crossedDay) await load()
  } catch (e) { if (token === summaryGeneration) ElMessage.error(e instanceof Error ? e.message : '摘要加载失败') }
}
async function refresh() { await Promise.all([load(), refreshSummary()]); notifyChanged() }
function focus() { if (!document.hidden) void refresh() }
let timer: ReturnType<typeof setInterval>
onMounted(() => { void refreshSummary(); window.addEventListener('focus', focus); document.addEventListener('visibilitychange', focus); timer = setInterval(() => { if (!document.hidden) void refreshSummary() }, 60000) })
onUnmounted(() => { summaryGeneration++; clearInterval(timer); window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', focus) })
</script>
<template>
  <div class="page">
    <h2>我的工作</h2>
    <el-card class="section-card" shadow="never">
    <p class="meta">按当前任务状态计算；分类可能重叠。服务端日期 {{ summary?.today }} · 获取时间 {{ fetchedAt }}</p>
    <div class="toolbar"><el-button v-for="(label, key) in labels" :key="key" :type="category === key ? 'primary' : 'default'" @click="category = key">{{ label }} {{ summary?.counts[key] ?? '—' }}</el-button></div>
    <p v-if="category === 'unblocked'">前置依赖已完成；仍需检查未完成子任务及提交条件。</p>
    </el-card>
    <ActionCardList :busy="actionBusy" :items="missions" :total="total" :loading="loading" v-model:page="page" v-model:page-size="pageSize" v-model:selected-ids="selectedIds" :reset-key="resetKey" empty-text="暂无任务">
      <template #filters><MissionQuickFilters :query="filters" @apply="apply" /></template>
      <template #actions><BulkMissionEditor @update:busy="actionBusy = $event" :missions="missions" v-model:selected-ids="selectedIds" :reset-key="resetKey" @changed="refresh" /></template>
      <template #item="{ item: mission }"><MissionCard :mission="mission" open-in-drawer @open="selected = $event">
        <template #selection><CardListSelection :id="mission.id" :label="`选择 ${mission.title}`" /></template>
        <template #details><p v-if="mission.unfinished_child_ids?.length" class="meta">仍有 {{ mission.unfinished_child_ids.length }} 个未完成子任务</p></template>
      </MissionCard></template>
    </ActionCardList>
    <MissionDetailDrawer :mission-id="selected" :open="!!selected" @close="selected = null" @changed="refresh" @focus="selected = $event" />
  </div>
</template>
