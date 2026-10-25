<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { workSummary, workMissions, notifyChanged, type WorkCategory, type WorkSummary } from '../api/notifications'
import type { Mission } from '../api/types'
import BulkMissionEditor from '../components/BulkMissionEditor.vue'
import MissionCard from '../components/MissionCard.vue'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
const labels: Record<WorkCategory, string> = { review: '待我验收', returned: '被退回', due_soon: '即将到期', overdue: '已逾期', unblocked: '依赖已解除', revalidation: '需要复核' }
const category = ref<WorkCategory>('review')
const summary = ref<WorkSummary | null>(null)
const missions = ref<Mission[]>([])
const page = ref(1), total = ref(0), loading = ref(false), fetchedAt = ref('')
const selected = ref<string | null>(null)
const selectedIds = ref<string[]>([])
const resetKey = computed(() => `${category.value}:${page.value}`)
let generation = 0, summaryGeneration = 0
async function load() {
  const token = ++generation
  loading.value = true
  try { const data = await workMissions(category.value, page.value); if (token === generation) { missions.value = data.results; total.value = data.count } }
  catch (e) { if (token === generation) ElMessage.error(e instanceof Error ? e.message : '任务加载失败') }
  finally { if (token === generation) loading.value = false }
}
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
watch(category, () => { page.value = 1; missions.value = []; total.value = 0; void load() })
let timer: ReturnType<typeof setInterval>
onMounted(() => { void refresh(); window.addEventListener('focus', focus); document.addEventListener('visibilitychange', focus); timer = setInterval(() => { if (!document.hidden) void refreshSummary() }, 60000) })
onUnmounted(() => { generation++; summaryGeneration++; clearInterval(timer); window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', focus) })
</script>
<template>
  <div class="page">
    <h2>我的工作</h2>
    <p class="meta">按当前任务状态计算；分类可能重叠。服务端日期 {{ summary?.today }} · 获取时间 {{ fetchedAt }}</p>
    <div class="toolbar"><el-button v-for="(label, key) in labels" :key="key" :type="category === key ? 'primary' : 'default'" @click="category = key">{{ label }} {{ summary?.counts[key] ?? '—' }}</el-button></div>
    <p v-if="category === 'unblocked'">前置依赖已完成；仍需检查未完成子任务及提交条件。</p>
    <BulkMissionEditor :missions="missions" v-model:selected-ids="selectedIds" :reset-key="resetKey" @changed="refresh" />
    <div v-loading="loading">
      <el-empty v-if="!loading && !missions.length" description="当前分类暂无任务" />
      <el-checkbox-group v-model="selectedIds" :max="50"><div v-for="mission in missions" :key="mission.id"><el-checkbox :value="mission.id" :label="mission.id">选择 {{ mission.title }}</el-checkbox><el-button link @click="selected = mission.id">打开详情抽屉</el-button><MissionCard :mission="mission" open-in-drawer @open="selected = $event" /><p v-if="mission.unfinished_child_ids?.length" class="meta">仍有 {{ mission.unfinished_child_ids.length }} 个未完成子任务</p></div></el-checkbox-group>
    </div>
    <el-pagination :total="total" :page-size="20" :current-page="page" layout="prev, pager, next" @current-change="page = $event; load()" />
    <MissionDetailDrawer :mission-id="selected" :open="!!selected" @close="selected = null" @changed="refresh" @focus="selected = $event" />
  </div>
</template>
