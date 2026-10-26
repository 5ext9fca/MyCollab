<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getInteraction, sendInteraction } from '../api/interactions'
import { ApiException } from '../api/client'
import type { InteractionState, InteractionEvent, InteractionInput, InteractionPermission } from '../api/interactions'
const props = defineProps<{ requestId: string; status: string }>()
const state = ref<InteractionState | null>(null)
const events = ref<InteractionEvent[]>([])
const draft = ref(''), error = ref(''), busy = ref(false)
const pending = ref<InteractionInput | null>(null)
const labels: Record<string, string> = { queued: '等待本地处理', applied: '本地已处理', rejected: '本地拒绝处理', expired: '已过期', pending: '待审批', decided: '决定已排队，等待本地处理', approved: '本地已批准一次', denied: '已拒绝', cancelled: '已取消' }
const timeline = computed(() => [
  ...events.value.filter(event => event.kind === 'assistant_message').map(event => ({ id: `event-${event.seq}`, time: event.created_at, title: 'Agent', text: event.payload.text })),
  ...(state.value?.commands ?? []).map(command => ({ id: command.command_id, time: command.created_at,
    title: `${command.kind === 'followup' ? '我的消息' : '我的审批'} · ${labels[command.status] ?? command.status}`,
    text: command.payload.text ?? (command.payload.decision === 'approve' ? '仅批准这一次' : '拒绝') })),
].sort((a, b) => Date.parse(a.time) - Date.parse(b.time)))
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false, generation = 0, cursor = 0, failures = 0, loadSequence = 0
async function load() {
  const current = generation, sequence = ++loadSequence
  clearTimeout(timer)
  try {
    const result = await getInteraction(props.requestId, cursor)
    if (disposed || current !== generation || sequence !== loadSequence) return
    state.value = result
    const known = new Set(events.value.map(e => e.seq))
    events.value.push(...result.events.filter(e => !known.has(e.seq)))
    cursor = result.next_cursor ?? cursor
    failures = 0
    if (result.has_more) timer = setTimeout(load, 100)
    else if (props.status === 'running' && (!result.available || result.active)) timer = setTimeout(load, 5000)
  } catch (err) {
    if (disposed || current !== generation || sequence !== loadSequence) return
    error.value = err instanceof Error ? err.message : '交互状态读取失败'
    if (props.status === 'running') timer = setTimeout(load, Math.min(60000, 5000 * 2 ** failures++))
  }
}
async function submit(input?: InteractionInput) {
  if (busy.value) return
  if (input) pending.value = input
  if (!pending.value) return
  busy.value = true; error.value = ''
  const current = generation
  try {
    await sendInteraction(props.requestId, pending.value)
    if (disposed || current !== generation) return
    if (pending.value.kind === 'followup') draft.value = ''
    pending.value = null
    await load()
  } catch (err) {
    if (!disposed && current === generation) {
      error.value = err instanceof Error ? err.message : '发送未确认，请重试同一指令'
      if (err instanceof ApiException && err.status >= 400 && err.status < 500) {
        pending.value = null
        await load()
      }
    }
  } finally { if (current === generation) busy.value = false }
}
function input(kind: InteractionInput['kind'], payload: InteractionInput['payload']): InteractionInput | undefined {
  if (!state.value?.active || !state.value.attempt_id || !state.value.session_nonce) return
  return { attempt_id: state.value.attempt_id, session_nonce: state.value.session_nonce, command_id: crypto.randomUUID(), kind, payload }
}
function followup() {
  if (!draft.value.trim() || pending.value || !state.value?.supports_followup) return
  const value = input('followup', { text: draft.value })
  if (value) void submit(value)
}
function decide(permission: InteractionPermission, decision: 'approve' | 'deny') {
  if (pending.value || permission.status !== 'pending' || Date.parse(permission.expires_at) <= Date.now()) return
  const value = input('permission_reply', { permission_id: permission.permission_id, operation_digest: permission.operation_digest, decision })
  if (value) void submit(value)
}
watch([() => props.requestId, () => props.status], () => {
  generation++; clearTimeout(timer); state.value = null; events.value = []; cursor = 0; failures = 0
  pending.value = null; draft.value = ''; error.value = ''; busy.value = false
  void load()
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer) })
</script>
<template>
  <el-card shadow="never" class="conversation">
    <h4>执行中对话与权限审批（仅本人可见）</h4>
    <p>消息由本地 Agent 接收，可能在当前工具步骤结束后处理。审批只针对列出的本地允许操作，不授予永久权限。</p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <p v-if="state && !state.available">本地 Runner 尚未启用交互，或当前适配器不支持。</p>
    <p v-else-if="state && !state.active">交互已结束或执行已失效；不能续写或批准操作。</p>
    <div v-for="message in timeline" :key="message.id" class="message"><strong>{{ message.title }} · {{ new Date(message.time).toLocaleString() }}</strong><pre>{{ message.text }}</pre></div>
    <el-card v-for="permission in state?.permissions" :key="permission.permission_id" shadow="never" class="permission">
      <h4>编辑文件审批 · {{ labels[permission.status] ?? permission.status }}</h4>
      <ul><li v-for="path in permission.operation.paths" :key="path">{{ path }}</li></ul>
      <p>有效期至 {{ new Date(permission.expires_at).toLocaleString() }}；超时默认拒绝。</p>
      <template v-if="state?.active && state.supports_permissions && permission.status === 'pending'">
        <el-button :disabled="busy || !!pending" @click="decide(permission, 'deny')">拒绝</el-button>
        <el-button type="primary" :disabled="busy || !!pending" @click="decide(permission, 'approve')">仅批准这一次</el-button>
      </template>
    </el-card>
    <template v-if="state?.active && state.supports_followup">
      <el-input v-model="draft" aria-label="执行中消息" type="textarea" :rows="3" maxlength="4000" :disabled="busy || !!pending" placeholder="补充要求或询问当前实现；不要发送凭据" />
      <el-button :disabled="busy || !!pending || !draft.trim()" @click="followup">发送消息</el-button>
    </template>
    <el-alert v-if="pending" type="warning" title="发送结果尚未确认，重试会沿用同一指令编号。" :closable="false" />
    <el-button v-if="pending" :loading="busy" @click="submit()">重试同一指令</el-button>
    <el-button :disabled="busy" @click="load">刷新对话</el-button>
  </el-card>
</template>
<style scoped>
.conversation, .permission { margin-top: 16px; }
.message { padding: 12px 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.el-button { margin-top: 8px; }
</style>
