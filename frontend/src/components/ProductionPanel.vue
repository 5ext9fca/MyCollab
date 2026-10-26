<script setup lang="ts">
import BlockedLink from './BlockedLink.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiException } from '../api/client'
import { listMilestones } from '../api/milestones'
import { getProduction, instantiateProduction, listProductionTemplates } from '../api/productionTemplates'
import type { DesignElement, Milestone, ProductionData, ProductionTemplate } from '../api/types'
import StatusTag from './StatusTag.vue'
import MarkdownContent from './MarkdownContent.vue'
const props = defineProps<{ asset: DesignElement }>()
const emit = defineEmits<{ (e: 'open', id: string): void; (e: 'changed'): void; (e: 'batch-loaded', present: boolean): void }>()
const production = ref<ProductionData>({ batch: null, items: [] })
const loading = ref(false)
const error = ref('')
const templates = ref<ProductionTemplate[]>([])
const templateId = ref<string | null>(null)
const template = computed(() => templates.value.find(item => item.id === templateId.value))
const query = ref('')
const templatePage = ref(1)
const moreTemplates = ref(false)
const milestones = ref<Milestone[]>([])
const milestonePage = ref(0)
const moreMilestones = ref(false)
const milestoneId = ref<string | null>(null)
const confirming = ref(false)
const saving = ref(false)
let seq = 0
let searchSeq = 0
let milestoneSeq = 0
const canGenerate = computed(() => !props.asset.archived && props.asset.allowed_actions.includes('edit') && !production.value.batch)
async function load() {
  const current = ++seq; loading.value = true; error.value = ''
  try { const data = await getProduction(props.asset.id); if (current === seq) { production.value = data; emit('batch-loaded', !!data.batch) } }
  catch (err) { if (current === seq) error.value = err instanceof ApiException ? err.message : '加载生产步骤失败' }
  finally { if (current === seq) loading.value = false }
}
async function searchTemplates(q = '', append = false) {
  const current = ++searchSeq
  if (!append) { templatePage.value = 1; query.value = q }
  try {
    const result = await listProductionTemplates({ q: query.value, page: templatePage.value })
    if (current !== searchSeq) return
    templates.value = append ? [...templates.value, ...result.results] : result.results
    moreTemplates.value = !!result.next
  } catch { ElMessage.error('加载模板失败') }
}
async function loadMilestones() {
  const current = ++milestoneSeq
  try {
    const result = await listMilestones({ page: milestonePage.value + 1, page_size: 100 })
    if (current !== milestoneSeq) return
    milestones.value.push(...result.results.filter(m => ['Planned', 'Active'].includes(m.status)))
    milestonePage.value++; moreMilestones.value = !!result.next
  } catch { ElMessage.error('加载里程碑失败') }
}
async function generate() {
  if (!template.value || saving.value) return
  saving.value = true
  try {
    await instantiateProduction(props.asset.id, { template_id: template.value.id, template_version: template.value.version, expected_version: props.asset.version, milestone_id: milestoneId.value })
    confirming.value = false; await load(); emit('changed'); ElMessage.success('生产任务已发布，可分别认领')
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? Object.values(err.fieldErrors).flat().join('；') || err.message : '生成失败')
    if (err instanceof ApiException && err.status === 409) { confirming.value = false; await load(); await searchTemplates(); emit('changed') }
  } finally { saving.value = false }
}
watch(() => props.asset.id, () => { templateId.value = null; milestoneId.value = null; confirming.value = false; milestones.value = []; milestonePage.value = 0; void searchTemplates(); void loadMilestones() }, { immediate: true })
watch(() => [props.asset.id, props.asset.version, props.asset.progress], load, { immediate: true })
onBeforeUnmount(() => { seq++; searchSeq++; milestoneSeq++ })
</script>
<template>
  <el-card class="section-card" shadow="never" v-loading="loading">
    <h3>资产生产步骤</h3>
    <el-alert v-if="error" :title="error" type="error" :closable="false" /><el-button v-if="error" @click="load">重试</el-button>
    <template v-if="production.batch">
      <p>模板：{{ production.batch.template_snapshot.name }} · 版本 {{ production.batch.template_version }}。模板后续修改不会改变本批任务。</p>
      <ol><li v-for="item in production.items" :key="item.step_key" class="production-step">
        <button type="button" class="app-link app-link--title" @click="emit('open', item.mission.id)">{{ item.mission.title }}</button> <StatusTag :status="item.mission.status" />
        <p>{{ item.mission.assignee?.display_name ?? '待认领' }}<BlockedLink v-if="item.mission.is_blocked" :mission-id="item.mission.id" /><span v-if="item.mission.needs_dependency_review"> · 需复核</span></p>
        <p>前置步骤：{{ item.mission.prerequisites?.map(p => p.title).join('、') || '无，可并行' }}</p>
        <el-button @click="emit('open', item.mission.id)">查看任务、成果与验收历史</el-button>
      </li></ol>
    </template>
    <template v-else-if="!loading && !error">
      <p>尚未生成生产任务。每项资产只可生成一批，之后可另行发布普通 Mission。</p>
      <div v-if="canGenerate" class="toolbar">
        <el-select v-model="templateId" filterable remote :remote-method="searchTemplates" placeholder="选择生产模板" style="min-width: 220px"><el-option v-for="item in templates" :key="item.id" :value="item.id" :label="`${item.name}（${item.steps.length} 步）`" /><template #footer><el-button class="app-link app-link--action" v-if="moreTemplates" link @click="templatePage++; searchTemplates(query, true)">加载更多</el-button></template></el-select>
        <el-select v-model="milestoneId" clearable placeholder="可选目标里程碑"><el-option v-for="item in milestones" :key="item.id" :value="item.id" :label="item.name" /><template #footer><el-button class="app-link app-link--action" v-if="moreMilestones" link @click="loadMilestones">加载更多</el-button></template></el-select>
        <el-button :disabled="!template" @click="confirming = true">预览生产步骤</el-button>
      </div>
    </template>
    <el-dialog v-model="confirming" title="确认生成生产任务" width="min(720px, 95vw)" :close-on-click-modal="!saving">
      <template v-if="template"><p>{{ template.name }} · 版本 {{ template.version }} · 目标里程碑：{{ milestones.find(m => m.id === milestoneId)?.name ?? '未关联' }}</p><p>将生成 {{ template.steps.length }} 个无人认领的 Mission，不自动分配成员或排期。</p>
        <ol><li v-for="step in template.steps" :key="step.key"><strong>{{ asset.title }} · {{ step.title }}</strong><p>前置：{{ step.prerequisite_keys.map(key => template!.steps.find(s => s.key === key)?.title ?? key).join('、') || '无，可并行' }}</p><MarkdownContent :source="step.content" /><p>验收标准</p><MarkdownContent :source="step.acceptance_criteria" /></li></ol>
        <el-button type="primary" :loading="saving" :disabled="!canGenerate" @click="generate">生成 {{ template.steps.length }} 个待认领 Mission</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
<style scoped>.production-step { padding: 12px 0; border-bottom: 1px solid var(--el-border-color-light); }</style>
