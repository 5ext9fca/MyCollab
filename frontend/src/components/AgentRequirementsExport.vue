<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ApiException } from '../api/client'
import { listAgentDevices, createAssistance, getAssistance, cancelAssistance } from '../api/agentBridge'
import type { AgentDevice, AssistanceInput, AssistanceRequest } from '../api/agentBridge'
import type { Mission } from '../api/types'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps<{ mission: Mission }>()
const devices = ref<AgentDevice[] | null>(null)
const deviceId = ref('')
const item = ref<AssistanceRequest | null>(null)
const pending = ref<AssistanceInput | null>(null)
const sourceVersion = ref<number | null>(null)
const busy = ref(false), error = ref('')
const active = computed(() => !!item.value && ['queued', 'running'].includes(item.value.status))
const markdown = computed(() => item.value?.status === 'succeeded' && typeof item.value.result?.markdown === 'string' ? item.value.result.markdown : '')
const outdated = computed(() => sourceVersion.value !== null && sourceVersion.value !== props.mission.version)
const labels: Record<string, string> = { queued: '等待本地 Agent 领取', running: '本地 LLM 正在整理需求文档', succeeded: '需求文档已整理，可预览并下载', failed: '整理失败，请检查本地环境后明确重试', cancelled: '已取消', expired: '请求已过期，请明确重试' }
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false, failures = 0, sequence = 0
function report(err: unknown) { error.value = err instanceof Error ? err.message : '操作失败，请重试。' }
function schedule(delay = 5000) { clearTimeout(timer); if (!disposed && active.value) timer = setTimeout(refresh, delay) }
async function refresh() {
  if (!item.value || disposed) return
  const current = ++sequence
  clearTimeout(timer)
  try {
    const result = await getAssistance(item.value.id)
    if (disposed || current !== sequence) return
    item.value = result; failures = 0; error.value = ''
  } catch (err) {
    if (disposed || current !== sequence) return
    report(err); failures++
  }
  schedule(Math.min(60000, 5000 * 2 ** failures))
}
async function generate() {
  if (busy.value || active.value) return
  busy.value = true; error.value = ''; clearTimeout(timer); sequence++
  try {
    if (!pending.value) {
      devices.value = (await listAgentDevices()).results.filter(d => !d.revoked_at && Date.parse(d.expires_at) > Date.now() && d.capabilities.includes('agent_requirements'))
      if (disposed) return
      if (!devices.value.length) { error.value = '请先绑定声明“Agent 需求文档”能力的本地设备，并启动更新后的 Runner。'; return }
      if (!devices.value.some(d => d.id === deviceId.value)) deviceId.value = devices.value.length === 1 ? devices.value[0]!.id : ''
      if (!deviceId.value) { error.value = '请选择用于整理文档的本地设备，再点击导出。'; return }
      pending.value = { device_id: deviceId.value, kind: 'agent_requirements', idempotency_key: crypto.randomUUID(), draft: {}, instructions: '', context_ids: [], object_id: props.mission.id, base_version: props.mission.version, retry_of: item.value?.id }
    }
    sourceVersion.value = pending.value.base_version ?? null
    const result = await createAssistance(pending.value)
    if (disposed) return
    item.value = result; pending.value = null; failures = 0; schedule()
  } catch (err) {
    if (disposed) return
    if (err instanceof ApiException && err.status < 500) pending.value = null
    report(err)
  } finally { if (!disposed) busy.value = false }
}
async function cancel() {
  if (!item.value || busy.value) return
  busy.value = true; sequence++; clearTimeout(timer)
  try { const result = await cancelAssistance(item.value.id); if (!disposed) item.value = result }
  catch (err) { if (!disposed) report(err) }
  finally { if (!disposed) { busy.value = false; schedule() } }
}
async function download() {
  if (!item.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const result = await getAssistance(item.value.id)
    if (disposed) return
    item.value = result
    if (outdated.value || result.stale_reason || result.status !== 'succeeded' || !markdown.value) throw new Error(result.stale_reason || '需求来源已变化或文档不可用，请刷新 Mission 后重新导出。')
    const url = URL.createObjectURL(new Blob([markdown.value], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url; link.download = `mission-${props.mission.id}-v${sourceVersion.value}-agent.md`
    document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) { if (!disposed) report(err) }
  finally { if (!disposed) busy.value = false }
}
onBeforeUnmount(() => { disposed = true; sequence++; clearTimeout(timer) })
</script>
<template>
  <el-card shadow="never" class="requirements-export">
    <h3>Agent 需求文档</h3>
    <p>由本地 LLM 整理当前 Mission、关联设计和资产说明，生成适合 Agent 阅读的 Markdown。仅整理文本；素材链接不会被自动读取。</p>
    <el-select v-if="devices?.length" v-model="deviceId" aria-label="文档整理设备" placeholder="选择本地设备" :disabled="active || busy || !!pending"><el-option v-for="device in devices" :key="device.id" :value="device.id" :label="device.name" /></el-select>
    <div class="actions">
      <el-button type="primary" :loading="busy" :disabled="active" @click="generate">导出为Agent需求文档</el-button>
      <el-button v-if="active" :disabled="busy" @click="cancel">取消整理</el-button>
      <el-button v-if="item" :disabled="busy" @click="refresh">刷新状态</el-button>
      <el-button v-if="markdown" :disabled="busy || outdated || !!item?.stale_reason" @click="download">下载 Markdown</el-button>
    </div>
    <router-link v-if="devices !== null" class="app-link" to="/agent-devices">管理本地 Agent 设备</router-link>
    <p v-if="item">{{ labels[item.status] }} · 来源版本 {{ sourceVersion }}。再次导出会创建新的整理请求。</p>
    <el-alert v-if="pending" title="请求是否创建尚未确认；再次导出会重发同一请求，不重复调用模型。" type="warning" :closable="false" />
    <el-alert v-if="outdated || item?.stale_reason" :title="item?.stale_reason || 'Mission 版本已变化，请重新导出。'" type="warning" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <MarkdownContent v-if="markdown" :source="markdown" />
  </el-card>
</template>
<style scoped>
.requirements-export { margin: 16px 0; }
.requirements-export :deep(.el-card__body) { display: grid; gap: 12px; }
h3, p { margin: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions .el-button { margin-left: 0; }
</style>
