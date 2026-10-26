<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ApiException } from '../api/client'
import { listAgentDevices, createAssistance, getAssistance, cancelAssistance } from '../api/agentBridge'
import type { AgentDevice, AssistanceKind, AssistanceRequest, AssistanceInput } from '../api/agentBridge'
import { getDesignElement } from '../api/designElements'
import { getMission } from '../api/missions'
import { listComments } from '../api/comments'
import type { Comment } from '../api/types'
import ElementMultiSelect from './ElementMultiSelect.vue'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps<{
  kind: AssistanceKind; draft: Record<string, unknown>; objectId?: string | null
  baseVersion?: number; submissionId?: string | null; parentId?: string | null
  reviewContext?: unknown
  currentComment?: string
}>()
const emit = defineEmits<{ adopt: [field: string, value: unknown] }>()
const devices = ref<AgentDevice[]>([])
const deviceId = ref('')
const instructions = ref('')
const designIds = ref<string[]>([])
const assetIds = ref<string[]>([])
const commentIds = ref<string[]>([])
const comments = ref<Comment[]>([])
const commentPage = ref(0)
const moreComments = ref(true)
const includeParent = ref(false)
const item = ref<AssistanceRequest | null>(null)
const busy = ref(false)
const error = ref('')
const preview = ref('')
const prepared = ref('')
const original = ref<Record<string, unknown>>({})
const originalComment = ref('')
const changedAcknowledged = ref(false)
const pendingInput = ref<AssistanceInput | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const active = computed(() => item.value && ['queued', 'running'].includes(item.value.status))
const changed = computed(() => !!item.value && (JSON.stringify(props.draft) !== JSON.stringify(original.value) || (props.currentComment ?? '') !== originalComment.value))
const device = computed(() => devices.value.find(d => d.id === deviceId.value))
const lastContact = computed(() => device.value?.last_seen_at ? new Date(device.value.last_seen_at).toLocaleString() : '尚未联系')
const labels: Record<string, string> = { title: '标题', content: '说明', name: '模板名称', description: '模板说明', steps: '生产步骤', acceptance_criteria: '验收标准', type: '任务类型', priority: '优先级', tags: '标签', comment: '验收意见草稿', questions: '待澄清问题', summary: '修改摘要', criteria: '逐项分析', missing_materials: '缺失材料', checks: '建议核对步骤' }
const statuses: Record<string, string> = { queued: '等待本地设备', running: '本地处理中', succeeded: '候选已返回，尚未保存', failed: '生成失败', expired: '请求过期，请明确重试', cancelled: '已取消' }
const assessments: Record<string, string> = { supported: '材料支持', contradicted: '材料存在矛盾', insufficient: '证据不足' }
interface ReviewCriterion { criterion: string; assessment: string; evidence: { path: string; quote: string }[]; unverified: string[] }
const reviewCriteria = computed(() => (item.value?.result?.criteria ?? []) as ReviewCriterion[])
const adoptable = computed(() => props.kind === 'review_assist' ? ['comment'] : props.kind === 'design_polish' ? ['title', 'content'] : props.kind === 'template_generate' ? ['name', 'description', 'steps'] : ['title', 'content', 'acceptance_criteria', 'type', 'priority', 'tags'])
function describe(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2) }
function report(err: unknown) { error.value = err instanceof ApiException ? Object.values(err.fieldErrors).flat().join('；') || err.message : '连接失败，可刷新状态后重试。' }
function signature() { return JSON.stringify([props.draft, instructions.value, designIds.value, assetIds.value, commentIds.value, includeParent.value, props.objectId, props.baseVersion, props.submissionId]) }
async function loadComments() {
  if (!props.objectId) return
  try { const data = await listComments(props.objectId, { page: commentPage.value + 1 }); comments.value.push(...data.results); commentPage.value++; moreComments.value = !!data.next } catch (err) { report(err) }
}
async function prepare() {
  error.value = ''; busy.value = true
  const snapshot = signature()
  try {
    const contexts = await Promise.all([...designIds.value, ...assetIds.value].map(getDesignElement))
    if (snapshot !== signature()) { error.value = '预览期间输入已改变，请重新预览。'; return }
    const parent = includeParent.value && props.parentId ? await getMission(props.parentId) : null
    if (snapshot !== signature()) { error.value = '预览期间输入已改变，请重新预览。'; return }
    preview.value = JSON.stringify({ draft: props.draft, instructions: instructions.value, contexts: contexts.map(c => ({ title: c.title, content: c.content, kind: c.kind })), parent: parent ? { title: parent.title, content: parent.content, acceptance_criteria: parent.acceptance_criteria } : null, review: props.reviewContext, comments: comments.value.filter(c => commentIds.value.includes(c.id)).map(c => ({ id: c.id, content: c.content })) }, null, 2)
    prepared.value = snapshot
  } catch (err) { report(err) } finally { busy.value = false }
}
async function refresh() {
  if (!item.value) return
  try { const updated = await getAssistance(item.value.id); if (!disposed) item.value = updated }
  catch (err) { if (!disposed) report(err) }
  if (!disposed && active.value) timer = setTimeout(refresh, 5000)
}
async function generate() {
  if (prepared.value !== signature()) { error.value = '输入已改变，请重新预览后生成。'; return }
  busy.value = true; error.value = ''; clearTimeout(timer)
  try {
    original.value = JSON.parse(JSON.stringify(props.draft)); changedAcknowledged.value = false
    originalComment.value = props.currentComment ?? ''
    pendingInput.value ??= JSON.parse(JSON.stringify({ device_id: deviceId.value, kind: props.kind, idempotency_key: crypto.randomUUID(), draft: props.draft,
      instructions: instructions.value, context_ids: [...designIds.value, ...assetIds.value], comment_ids: commentIds.value, object_id: props.objectId,
      base_version: props.objectId ? props.baseVersion : null, submission_id: props.submissionId,
      parent_id: includeParent.value ? props.parentId : null, retry_of: item.value?.id })) as AssistanceInput
    item.value = await createAssistance(pendingInput.value)
    original.value = JSON.parse(JSON.stringify(pendingInput.value.draft))
    pendingInput.value = null
    if (!disposed) timer = setTimeout(refresh, 3000)
  } catch (err) {
    if (err instanceof ApiException && err.status < 500) pendingInput.value = null
    report(err)
  } finally { busy.value = false }
}
async function cancel() {
  if (!item.value) return
  busy.value = true; clearTimeout(timer)
  try { item.value = await cancelAssistance(item.value.id) } catch (err) { report(err) } finally { busy.value = false }
}
async function adopt(field: string) {
  if (!item.value || !adoptable.value.includes(field)) return
  busy.value = true
  try {
    item.value = await getAssistance(item.value.id)
    if (item.value.stale_reason || item.value.status !== 'succeeded') { error.value = item.value.stale_reason || '当前结果不能采纳。'; return }
    if (changed.value && !changedAcknowledged.value) { error.value = '请先确认已比较当前草稿。'; return }
    emit('adopt', field, item.value.result?.[field])
  } catch (err) { report(err) } finally { busy.value = false }
}
onMounted(async () => {
  try { devices.value = (await listAgentDevices()).results.filter(d => !d.revoked_at && Date.parse(d.expires_at) > Date.now() && d.capabilities.includes(props.kind)); deviceId.value = devices.value[0]?.id ?? '' } catch (err) { report(err) }
})
onUnmounted(() => { disposed = true; clearTimeout(timer) })
</script>

<template>
  <el-card shadow="never" class="assistance-panel">
    <h3>本地 Agent 辅助</h3>
    <p>仅发送你确认的文本。模型调用与凭据保留在本地；建议需逐字段采纳并手动保存。</p>
    <router-link class="app-link app-link--action" to="/agent-devices">管理本地设备与请求记录</router-link>
    <el-select v-model="deviceId" aria-label="本地设备" placeholder="选择本人设备" :disabled="!!active"><el-option v-for="d in devices" :key="d.id" :value="d.id" :label="d.name" /></el-select>
    <el-alert type="info" :closable="false" :title="`最近联系：${lastContact}。联系记录不代表实时在线；请求由本地设备领取。`" />
    <el-input v-model="instructions" type="textarea" :rows="2" maxlength="10000" aria-label="辅助要求" placeholder="填写目标与补充要求" />
    <ElementMultiSelect v-model="designIds" kind="Design" label="交给 Agent 的设计说明" />
    <ElementMultiSelect v-model="assetIds" kind="Asset" label="交给 Agent 的资产说明" />
    <el-checkbox v-if="parentId" v-model="includeParent">附带父任务说明</el-checkbox>
    <template v-if="kind === 'review_assist'">
      <el-select v-model="commentIds" multiple :multiple-limit="20" placeholder="可选：只发送明确选中的评论" aria-label="验收评论上下文"><el-option v-for="comment in comments" :key="comment.id" :value="comment.id" :label="comment.content.slice(0, 100)" /></el-select>
      <el-button v-if="moreComments" @click="loadComments">加载可选评论</el-button>
    </template>
    <div class="assistance-actions"><el-button :loading="busy" :disabled="!!active" @click="prepare">预览发送内容</el-button><el-button :loading="busy" :disabled="!deviceId || !!active || !prepared || prepared !== signature()" @click="generate">{{ item ? '明确重试' : '生成候选' }}</el-button></div>
    <details v-if="preview"><summary>发送内容预览</summary><pre>{{ preview }}</pre></details>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-alert v-if="pendingInput" type="warning" title="请求是否创建尚未确认。再次点击将重发同一份输入，不会重新创建；也可在请求记录中查看。" :closable="false" />
    <template v-if="item">
      <p>{{ statuses[item.status] }}<template v-if="item.status === 'cancelled'"> · {{ item.stopped_at ? '本地已确认停止或未开始' : '等待本地确认停止' }}</template></p>
      <p v-if="item.error">{{ item.error }}</p>
      <el-alert v-if="item.stale_reason" type="warning" :title="item.stale_reason" :closable="false" />
      <div class="assistance-actions"><el-button v-if="active || item.status === 'succeeded'" :loading="busy" @click="cancel">{{ active ? '取消请求' : '放弃候选' }}</el-button><el-button v-if="!active" :loading="busy" @click="refresh">刷新状态</el-button></div>
      <el-checkbox v-if="changed" v-model="changedAcknowledged">草稿已改变，我已比较原文、当前内容与建议，按字段合并</el-checkbox>
      <div v-if="item.result && item.status === 'succeeded'" class="assistance-results">
        <section v-for="(value, field) in item.result" :key="field">
          <h4>{{ labels[field] ?? field }}</h4>
          <details v-if="field in original"><summary>生成时原文与当前内容</summary><pre>{{ describe(original[field]) }}</pre><pre>{{ describe(draft[field]) }}</pre></details>
          <template v-if="field === 'criteria'"><article v-for="(criterion, index) in reviewCriteria" :key="index"><h4>{{ criterion.criterion }} · {{ assessments[criterion.assessment] }}</h4><p v-for="evidence in criterion.evidence" :key="evidence.path + evidence.quote">依据 {{ evidence.path }}：{{ evidence.quote }}</p><p v-for="unverified in criterion.unverified" :key="unverified">未验证：{{ unverified }}</p></article></template>
          <MarkdownContent v-else-if="typeof value === 'string' && ['content', 'acceptance_criteria', 'comment', 'description'].includes(field)" :source="value" />
          <pre v-else>{{ describe(value) }}</pre>
          <el-button v-if="adoptable.includes(field)" :disabled="!!item.stale_reason || (changed && !changedAcknowledged)" :loading="busy" @click="adopt(field)">采纳{{ labels[field] }}</el-button>
        </section>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.assistance-panel { margin: 16px 0; }
.assistance-panel :deep(.el-card__body) { display: grid; gap: 12px; }
.assistance-panel h3, .assistance-panel p { margin: 0; }
.assistance-actions { display: flex; flex-wrap: wrap; gap: 8px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow: auto; }
.assistance-results { display: grid; gap: 16px; min-width: 0; }
</style>
