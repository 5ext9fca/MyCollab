<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listAgentDevices } from '../api/agentBridge'
import type { AgentDevice, ImageKind } from '../api/agentBridge'
import { getDesignElement } from '../api/designElements'
import { listLibraryFiles } from '../api/library'
import { cancelExecution, createExecution, getExecution, listExecutions } from '../api/executions'
import type { ExecutionCandidate, ExecutionInput, MissionExecution } from '../api/executions'
import type { LibraryFile, Mission } from '../api/types'

const props = defineProps<{ mission: Mission; canAdopt?: boolean }>()
const emit = defineEmits<{ adopt: [candidates: ExecutionCandidate[]] }>()
const auth = useAuthStore()
const eligible = computed(() => props.mission.status === 'InProgress' && props.mission.assignee?.id === auth.user?.id)
const assets = computed(() => (props.mission.assets ?? []).filter(a => !a.archived))
const devices = ref<AgentDevice[]>([])
const kind = ref<ImageKind>('image_generate')
const formDetails = ref<HTMLDetailsElement>()
const availableKinds = computed(() => (['image_generate', 'image_edit'] as ImageKind[]).filter(k => devices.value.some(d => !d.revoked_at && Date.parse(d.expires_at) > Date.now() && d.capabilities.includes(k))))
watch(availableKinds, kinds => { if (!kinds.includes(kind.value) && kinds[0]) kind.value = kinds[0] })
watch(kind, () => { deviceId.value = validDevices.value[0]?.id ?? '' })
const validDevices = computed(() => devices.value.filter(d => !d.revoked_at && Date.parse(d.expires_at) > Date.now() && d.capabilities.includes(kind.value)))
const deviceId = ref(''), assetId = ref(''), instructions = ref(''), previousId = ref<string | null>(null)
const files = ref<LibraryFile[]>([]), referenceIds = ref<string[]>([])
const filePage = ref(0), fileCount = ref(0)
const history = ref<MissionExecution[]>([]), page = ref(1), count = ref(0)
const prepared = ref<ExecutionInput | null>(null), preview = ref(''), error = ref(''), busy = ref(false)
const active = ['queued', 'running', 'awaiting_selection']
const labels: Record<MissionExecution['status'], string> = { queued: '等待本地设备', running: '本地生成中', awaiting_selection: '等待本地选择/上传', succeeded: '选中成果已上传', failed: '失败', cancelled: '已取消', expired: '已过期' }
let timer: ReturnType<typeof setTimeout> | undefined
let failures = 0, loadSequence = 0
let disposed = false
let generation = 0

function fail(err: unknown) { error.value = err instanceof Error ? err.message : '操作失败' }
async function load() {
  if (disposed) return
  const version = generation, sequence = ++loadSequence
  clearTimeout(timer)
  try {
    const result = await listExecutions(props.mission.id, page.value)
    if (disposed || version !== generation || sequence !== loadSequence) return
    failures = 0
    history.value = result.results; count.value = result.count
    if (history.value.some(e => active.includes(e.status))) timer = setTimeout(load, 15000)
  } catch (err) {
    if (!disposed && version === generation && sequence === loadSequence) {
      fail(err)
      timer = setTimeout(load, Math.min(60000, 15000 * 2 ** failures++))
    }
  }
}
async function loadFiles() {
  const version = generation
  try {
    const result = await listLibraryFiles({ page: filePage.value + 1, page_size: 100 })
    if (disposed || version !== generation) return
    filePage.value++; fileCount.value = result.count
    files.value.push(...result.results)
  } catch (err) { fail(err) }
}
const images = computed(() => files.value.filter(f => ['image/png', 'image/jpeg', 'image/webp'].includes(f.content_type) && f.size <= 20 * 1024 * 1024))
async function prepare() {
  error.value = ''; busy.value = true; prepared.value = null
  try {
    if (!eligible.value || !assets.value.some(a => a.id === assetId.value) || !validDevices.value.some(d => d.id === deviceId.value) || !instructions.value.trim()) throw new Error('请选择可用设备、相关资产并填写要求。')
    if (referenceIds.value.length > 4 || (kind.value === 'image_edit' && !referenceIds.value.length)) throw new Error('最多选择 4 张参考图；编辑至少选择 1 张。')
    const selected = files.value.filter(f => referenceIds.value.includes(f.id))
    if (selected.reduce((total, f) => total + f.size, 0) > 40 * 1024 * 1024) throw new Error('参考图总量不能超过 40 MiB。')
    const formVersion = JSON.stringify([props.mission.id, props.mission.version, kind.value, deviceId.value, assetId.value, instructions.value, referenceIds.value])
    const asset = await getDesignElement(assetId.value)
    if (disposed || !eligible.value || formVersion !== JSON.stringify([props.mission.id, props.mission.version, kind.value, deviceId.value, assetId.value, instructions.value, referenceIds.value])) throw new Error('委派内容已改变，请重新预览。')
    prepared.value = { mission_id: props.mission.id, expected_version: props.mission.version, asset_id: asset.id, asset_version: asset.version, device_id: deviceId.value, kind: kind.value, instructions: instructions.value, reference_ids: [...referenceIds.value], idempotency_key: crypto.randomUUID(), previous_id: previousId.value }
    preview.value = JSON.stringify({ mission: { id: props.mission.id, title: props.mission.title, content: props.mission.content, acceptance_criteria: props.mission.acceptance_criteria, version: props.mission.version }, asset: { id: asset.id, title: asset.title, content: asset.content, version: asset.version }, instructions: instructions.value, references: selected.map(f => ({ id: f.id, name: f.original_name, size: f.size, content_type: f.content_type })) }, null, 2)
  } catch (err) { fail(err) } finally { busy.value = false }
}
async function create() {
  const version = generation
  if (busy.value || !prepared.value || !eligible.value) return
  busy.value = true; error.value = ''
  try { await createExecution(prepared.value); if (disposed || version !== generation) return; prepared.value = null; preview.value = ''; previousId.value = null; page.value = 1; await load() }
  catch (err) { fail(err) } finally { busy.value = false }
}
async function cancel(id: string) { try { await cancelExecution(id); await load() } catch (err) { fail(err) } }
function retry(item: MissionExecution) { if (formDetails.value) formDetails.value.open = true; assetId.value = item.asset_id; kind.value = item.kind; previousId.value = item.id; prepared.value = null; preview.value = '' }
async function adopt(item: MissionExecution) {
  try {
    const current = await getExecution(item.id)
    if (disposed || current.mission_id !== props.mission.id || !eligible.value || current.actor_id !== auth.user?.id || current.status !== 'succeeded' || current.mission_version !== props.mission.version || current.stale_reason) throw new Error('成果当前不可引用，请刷新任务。')
    const asset = await getDesignElement(current.asset_id)
    if (disposed || current.mission_id !== props.mission.id || !eligible.value || current.mission_version !== props.mission.version || asset.archived || asset.version !== current.asset_version || !assets.value.some(a => a.id === asset.id)) throw new Error('资产已变化，请重新委派。')
    emit('adopt', current.candidates.filter(c => c.file_id && c.url))
  } catch (err) { fail(err) }
}
watch([kind, deviceId, assetId, instructions, referenceIds, () => props.mission.version], () => { prepared.value = null; preview.value = '' }, { deep: true })
watch([() => props.mission.id, eligible], async () => {
  const version = ++generation
  clearTimeout(timer)
  devices.value = []; deviceId.value = ''; instructions.value = ''
  failures = 0
  history.value = []; page.value = 1; prepared.value = null; preview.value = ''; previousId.value = null
  files.value = []; filePage.value = 0; referenceIds.value = []; error.value = ''; assetId.value = assets.value[0]?.id ?? ''
  await load()
  if (disposed || version !== generation) return
  if (eligible.value) {
    try { const result = await listAgentDevices()
      if (disposed || version !== generation) return
      devices.value = result.results; deviceId.value = validDevices.value[0]?.id ?? ''; await loadFiles() } catch (err) { fail(err) }
  }
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer) })
</script>
<template>
  <el-card shadow="never" class="execution-panel">
    <h3>美术资产委派</h3>
    <p>本地设备生成和预览图片。仅在本地明确选择后上传；成果仍需人工提交、验收。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <details v-if="eligible" ref="formDetails"><summary>创建图像委派</summary>
      <p v-if="!assets.length">请先为 Mission 关联未归档的 Asset。</p>
      <p v-if="!validDevices.length">暂无声明所选图像能力的设备，请在 <router-link class="app-link" to="/agent-devices">本地 Agent 设备</router-link> 中绑定。</p>
      <el-form v-if="validDevices.length && assets.length" label-position="top">
        <el-form-item label="操作"><el-radio-group v-model="kind"><el-radio v-if="availableKinds.includes('image_generate')" value="image_generate">生成图片</el-radio><el-radio v-if="availableKinds.includes('image_edit')" value="image_edit">编辑参考图</el-radio></el-radio-group></el-form-item>
        <el-form-item label="本地设备"><el-select v-model="deviceId"><el-option v-for="d in validDevices" :key="d.id" :value="d.id" :label="`${d.name}（${d.last_seen_at ? '最近联系：' + new Date(d.last_seen_at).toLocaleString() : '尚未联系'}）`" /></el-select></el-form-item>
        <el-form-item label="相关资产"><el-select v-model="assetId"><el-option v-for="a in assets" :key="a.id" :value="a.id" :label="a.title" /></el-select></el-form-item>
        <el-form-item label="制作要求"><el-input v-model="instructions" type="textarea" :rows="3" maxlength="10000" /></el-form-item>
        <el-form-item label="本人参考素材（最多 4 张，共 40 MiB）"><el-select v-model="referenceIds" multiple :multiple-limit="4" filterable><el-option v-for="f in images" :key="f.id" :value="f.id" :label="f.original_name" /></el-select><el-button v-if="files.length < fileCount" @click="loadFiles">加载更多素材</el-button></el-form-item>
        <p v-if="previousId">本次将创建新版本，并关联上一执行；不会覆盖旧成果。</p>
        <el-button :loading="busy" @click="prepare">预览委派内容</el-button>
      </el-form>
      <el-card v-if="prepared" shadow="never" class="preview"><h4>将发送到所选本地设备的材料</h4><pre>{{ preview }}</pre><p>设备离线时等待连接；服务器不会代为调用模型。</p><el-button type="primary" :loading="busy" @click="create">确认委派</el-button></el-card>
    </details>
    <p v-else>只有当前认领者可委派进行中的 Mission。</p>
    <h4>执行与成果历史</h4><el-button @click="load">刷新执行记录</el-button>
    <el-empty v-if="!history.length" description="暂无图像执行" :image-size="48" />
    <el-card v-for="item in history" :key="item.id" shadow="never" class="execution-item">
      <h4>{{ mission.assets?.find(a => a.id === item.asset_id)?.title ?? '历史资产' }} · 版本 {{ item.version }}</h4>
      <p>{{ labels[item.status] }} · {{ new Date(item.created_at).toLocaleString() }} · 有效期至 {{ new Date(item.expires_at).toLocaleString() }}</p>
      <p v-if="item.stale_reason || item.error">{{ item.stale_reason || item.error }}</p>
      <p v-if="item.status === 'cancelled'">{{ item.stopped_at ? '本地已确认停止或未开始' : '等待本地确认停止；取消不保证供应商立即停止' }}</p>
      <p v-if="item.status === 'awaiting_selection'">请在本地 Runner 打开的预览中检查候选，再用 --select {{ item.request_id }} --keys 候选编号 明确选择。有效期至 {{ new Date(item.expires_at).toLocaleString() }}。</p>
      <div class="candidates"><figure v-for="candidate in item.candidates" :key="candidate.id"><template v-if="candidate.url"><img :src="candidate.url" :alt="candidate.name" loading="lazy"><a class="app-link" :href="candidate.url" target="_blank" rel="noopener">{{ candidate.name }}</a></template><figcaption v-else>{{ candidate.key }} · {{ candidate.width }} × {{ candidate.height }} · 仅本地候选</figcaption></figure></div>
      <el-button v-if="item.actor_id === auth.user?.id && active.includes(item.status)" @click="cancel(item.id)">取消执行</el-button>
      <el-button v-if="eligible && item.actor_id === auth.user?.id && !active.includes(item.status)" @click="retry(item)">以新版本再次委派</el-button>
      <el-button v-if="canAdopt && eligible && item.actor_id === auth.user?.id && item.status === 'succeeded' && item.mission_version === mission.version" @click="adopt(item)">引用到提交草稿</el-button>
      <router-link v-if="!canAdopt && item.status === 'succeeded'" class="app-link" :to="`/missions/${mission.id}`">到完整详情提交成果</router-link>
    </el-card>
    <el-pagination v-if="count > 20" v-model:current-page="page" :total="count" :page-size="20" layout="prev, pager, next" @current-change="load" />
  </el-card>
</template>
<style scoped>
.execution-panel { margin: 16px 0; }
.execution-item, .preview { margin-top: 16px; }
summary { cursor: pointer; padding: 12px 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; }
.candidates { display: flex; flex-wrap: wrap; gap: 12px; }
figure { margin: 8px 0; max-width: 240px; }
figure img { display: block; max-width: 100%; max-height: 200px; margin-bottom: 8px; }
.el-button { margin-top: 8px; }
</style>
