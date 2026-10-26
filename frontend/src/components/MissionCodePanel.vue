<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listAgentDevices } from '../api/agentBridge'
import type { AgentDevice } from '../api/agentBridge'
import { createCodeExecution, listCodeExecutions, cancelCodeExecution, getCodeExecution } from '../api/codeExecutions'
import type { CodeExecution, CodeInput } from '../api/codeExecutions'
import type { Mission } from '../api/types'
import CodeReport from './CodeReport.vue'

const props = defineProps<{ mission: Mission; canAdopt?: boolean }>()
const emit = defineEmits<{ adopt: [execution: CodeExecution] }>()
const auth = useAuthStore()
const eligible = computed(() => props.mission.status === 'InProgress' && props.mission.assignee?.id === auth.user?.id)
const devices = ref<AgentDevice[]>([])
const validDevices = computed(() => devices.value.filter(d => d.capabilities.includes('code_implement') && !d.revoked_at && Date.parse(d.expires_at) > Date.now()))
const deviceId = ref(''), repositoryKey = ref(''), instructions = ref(''), previousId = ref<string | null>(null)
const prepared = ref<CodeInput | null>(null), preview = ref(''), error = ref(''), busy = ref(false)
const history = ref<CodeExecution[]>([]), page = ref(1), count = ref(0)
const formDetails = ref<HTMLDetailsElement>()
const active = ['queued', 'running', 'awaiting_selection']
const labels: Record<CodeExecution['status'], string> = { queued: '等待本地设备', running: '本地实现/验证中', awaiting_selection: '等待本地审查发布', succeeded: '补丁与报告已发布', failed: '失败', cancelled: '已取消', expired: '已过期' }
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0, disposed = false
function fail(err: unknown) { error.value = err instanceof Error ? err.message : '操作失败' }
async function load() {
  const version = generation
  clearTimeout(timer)
  try {
    const result = await listCodeExecutions(props.mission.id, page.value)
    if (disposed || version !== generation) return
    history.value = result.results; count.value = result.count
    if (history.value.some(e => active.includes(e.status))) timer = setTimeout(load, 15000)
  } catch (err) { if (!disposed && version === generation) fail(err) }
}
function prepare() {
  error.value = ''; prepared.value = null
  if (!eligible.value || !validDevices.value.some(d => d.id === deviceId.value) || !/^[A-Za-z0-9_-]{1,64}$/.test(repositoryKey.value) || !instructions.value.trim()) {
    error.value = '请选择可用设备、填写本地仓库标识与实现要求。仓库标识不能是路径或命令。'; return
  }
  prepared.value = { mission_id: props.mission.id, expected_version: props.mission.version, device_id: deviceId.value, repository_key: repositoryKey.value, instructions: instructions.value, previous_id: previousId.value, idempotency_key: crypto.randomUUID() }
  preview.value = JSON.stringify({ mission: { title: props.mission.title, content: props.mission.content, acceptance_criteria: props.mission.acceptance_criteria }, repository_key: repositoryKey.value, instructions: instructions.value }, null, 2)
}
async function create() {
  if (!prepared.value || !eligible.value) return
  error.value = ''; busy.value = true
  try { await createCodeExecution(prepared.value); prepared.value = null; preview.value = ''; previousId.value = null; page.value = 1; await load() }
  catch (err) { fail(err) } finally { busy.value = false }
}
async function cancel(item: CodeExecution) { try { await cancelCodeExecution(item.id); await load() } catch (err) { fail(err) } }
function retry(item: CodeExecution) {
  repositoryKey.value = item.repository_key; previousId.value = item.id; prepared.value = null; preview.value = ''
  if (formDetails.value) formDetails.value.open = true
}
async function adopt(item: CodeExecution) {
  try {
    const current = await getCodeExecution(item.id)
    if (!eligible.value || current.actor_id !== auth.user?.id || current.status !== 'succeeded' || !current.patch_url || !current.report || current.mission_version !== props.mission.version || current.stale_reason) throw new Error('代码成果不可引用，请刷新任务并检查版本。')
    emit('adopt', current)
  } catch (err) { fail(err) }
}
watch([deviceId, repositoryKey, instructions, () => props.mission.version], () => { prepared.value = null; preview.value = '' })
watch([() => props.mission.id, eligible], async () => {
  generation++; history.value = []; page.value = 1; prepared.value = null; preview.value = ''; error.value = ''; previousId.value = null
  await load()
  if (eligible.value) try { devices.value = (await listAgentDevices()).results; deviceId.value = validDevices.value[0]?.id ?? '' } catch (err) { fail(err) }
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer) })
</script>
<template>
  <el-card shadow="never" class="code-panel">
    <h3>规则/代码委派</h3><p>由本人本地 OpenCode 在隔离副本中实现。补丁和验证报告先留在本地，人工审查并发布后才能引用到提交草稿。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <details v-if="eligible" ref="formDetails"><summary>创建代码委派</summary>
      <p v-if="!validDevices.length">暂无声明代码实现能力的设备，请先在 <router-link class="app-link" to="/agent-devices">本地 Agent 设备</router-link> 中绑定。</p>
      <el-form label-position="top">
        <el-form-item label="本地设备"><el-select v-model="deviceId"><el-option v-for="d in validDevices" :key="d.id" :value="d.id" :label="`${d.name}（${d.last_seen_at && Date.now() - Date.parse(d.last_seen_at) < 120000 ? '最近在线' : '离线/待连接'}）`" /></el-select></el-form-item>
        <el-form-item label="本地仓库标识"><el-input v-model="repositoryKey" maxlength="64" placeholder="例如 game-rules；不是路径或 URL" /></el-form-item>
        <p>标识对应本地 Runner 已配置的仓库、基线、允许修改范围与验证命令。可在本机使用 --list-repositories 核对；服务器不会下发命令或读取本机配置。</p>
        <el-form-item label="实现要求"><el-input v-model="instructions" type="textarea" :rows="3" maxlength="10000" /></el-form-item>
        <p v-if="previousId">本次将创建新版本，并关联上一执行。</p>
        <el-button :loading="busy" @click="prepare">预览代码委派</el-button>
      </el-form>
      <el-card v-if="prepared" shadow="never" class="preview"><h4>将发送到本地设备的材料</h4><pre>{{ preview }}</pre><p>离线时等待连接。生成、验证和发布均不自动提交或验收 Mission。</p><el-button type="primary" :loading="busy" @click="create">确认代码委派</el-button></el-card>
    </details>
    <p v-else>只有当前认领者可委派进行中的 Mission。</p>
    <h4>代码执行历史</h4><el-button @click="load">刷新代码记录</el-button>
    <el-empty v-if="!history.length" description="暂无代码执行" :image-size="48" />
    <el-card v-for="item in history" :key="item.id" shadow="never" class="execution-item">
      <h4>{{ item.repository_key }} · 版本 {{ item.version }}</h4><p>{{ labels[item.status] }} · {{ new Date(item.created_at).toLocaleString() }}</p>
      <p v-if="item.error || item.stale_reason">{{ item.stale_reason || (item.error === 'no_changes' ? '未产生代码差异，请检查任务与本地基线。' : item.error) }}</p>
      <p v-if="item.status === 'awaiting_selection'">请在本机检查补丁与报告，再用 --publish-code {{ item.request_id }} 明确发布。有效期至 {{ new Date(item.expires_at).toLocaleString() }}。</p>
      <CodeReport v-if="item.report" :report="item.report" :patch-url="item.patch_url" />
      <el-button v-if="item.actor_id === auth.user?.id && active.includes(item.status)" @click="cancel(item)">取消代码执行</el-button>
      <el-button v-if="eligible && item.actor_id === auth.user?.id && !active.includes(item.status)" @click="retry(item)">以新版本再次委派代码</el-button>
      <el-button v-if="canAdopt && eligible && item.actor_id === auth.user?.id && item.status === 'succeeded' && item.mission_version === mission.version" @click="adopt(item)">引用代码成果到提交草稿</el-button>
      <router-link v-if="!canAdopt && item.status === 'succeeded'" class="app-link" :to="`/missions/${mission.id}`">到完整详情提交成果</router-link>
    </el-card>
    <el-pagination v-if="count > 20" v-model:current-page="page" :total="count" :page-size="20" layout="prev, pager, next" @current-change="load" />
  </el-card>
</template>
<style scoped>
.code-panel { margin: 16px 0; }
.execution-item, .preview { margin-top: 16px; }
summary { cursor: pointer; padding: 12px 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; }
.el-button { margin-top: 8px; }
</style>
