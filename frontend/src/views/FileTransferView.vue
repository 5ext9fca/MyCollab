<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import { TransferController, type TransferState } from '../transfers/controller'

const supported = typeof RTCPeerConnection !== 'undefined' && !!globalThis.crypto?.subtle
const file = shallowRef<File | null>(null)
const code = ref('')
const state = shallowRef<TransferState>({ session: null, busy: false, active: false, message: '', bytes: 0, checksum: '', downloadUrl: '', success: false })
let controller: TransferController | null = null
const progress = computed(() => state.value.success ? 100 : state.value.session?.size ? Math.min(100, Math.floor(state.value.bytes / state.value.session.size * 100)) : 0)
function start() {
  controller?.dispose()
  controller = new TransferController((next) => { state.value = next })
  return controller
}
function selectFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] ?? null }
function send() { if (file.value && !state.value.active) void start().send(file.value) }
function join() { if (code.value.trim() && !state.value.active) void start().join(code.value) }
function leave(event: BeforeUnloadEvent) { if (state.value.active) { event.preventDefault(); event.returnValue = '' } }
function pageHide() { controller?.dispose() }
window.addEventListener('beforeunload', leave)
window.addEventListener('pagehide', pageHide)
onBeforeUnmount(() => { window.removeEventListener('beforeunload', leave); window.removeEventListener('pagehide', pageHide); controller?.dispose() })
function size(bytes: number) { return `${bytes.toLocaleString()} 字节（${(bytes / 1024 / 1024).toFixed(2)} MiB）` }
</script>

<template>
  <div class="transfer-page">
    <el-card shadow="never">
      <template #header><h1>文件互传</h1></template>
      <p>双方登录并打开此页，通过配对码在局域网内直接传文件。支持同一账号的不同设备。浏览器或系统询问局域网访问权限时，请允许本站连接。</p>
      <p class="meta">单文件最多 100 MiB。请保持双方页面打开；中断后需重新发送。文件不保存到服务器，接收端完成 SHA-256 校验后才能下载。</p>
      <el-alert v-if="!supported" title="当前环境不支持直传或 SHA-256：请使用新版浏览器，通过 HTTPS 访问本站（本机开发可用 localhost）。" type="error" :closable="false" />
    </el-card>
    <div class="transfer-inputs">
      <el-card shadow="never">
        <template #header><h2>发送文件</h2></template>
        <label for="transfer-file">选择文件</label>
        <input id="transfer-file" type="file" :disabled="!supported || state.active" @change="selectFile" />
        <el-button type="primary" :disabled="!supported || !file || state.active" @click="send">生成配对码</el-button>
      </el-card>
      <el-card shadow="never">
        <template #header><h2>接收文件</h2></template>
        <el-form @submit.prevent="join">
          <el-form-item label="配对码">
            <el-input v-model="code" aria-label="配对码" maxlength="12" placeholder="输入发送方的 12 位配对码" :disabled="!supported || state.active" />
          </el-form-item>
          <el-button native-type="submit" type="primary" :disabled="!supported || code.trim().length !== 12 || state.active">查看待接收文件</el-button>
        </el-form>
      </el-card>
    </div>
    <el-card v-if="state.message || state.session" shadow="never">
      <template #header><h2>传输状态</h2></template>
      <p role="status" aria-live="polite">{{ state.message }}</p>
      <template v-if="state.session">
        <p v-if="state.session.code && ['waiting', 'paired'].includes(state.session.status) && state.active">配对码：<strong class="pair-code" data-testid="pair-code">{{ state.session.code }}</strong>（5 分钟内确认接收）</p>
        <p>文件：{{ state.session.name }}</p>
        <p>大小：{{ size(state.session.size) }}</p>
        <p>发送人：{{ state.session.sender_name }}<template v-if="state.session.receiver_name"> · 接收人：{{ state.session.receiver_name }}</template></p>
        <p>发送端 SHA-256：<code class="checksum">{{ state.session.sha256 }}</code></p>
        <p v-if="state.session.received_sha256">接收端 SHA-256：<code class="checksum">{{ state.session.received_sha256 }}</code></p>
        <el-progress :percentage="progress" :status="state.success ? 'success' : undefined" />
        <p class="meta">已处理 {{ size(state.bytes) }}；进度达到 100% 后仍需等待校验确认。</p>
        <el-button v-if="state.session.role === 'receiver' && state.session.status === 'paired' && state.active" type="primary" :loading="state.busy" @click="controller?.accept()">确认接收</el-button>
        <a v-if="state.success && state.downloadUrl" class="app-link app-link--action" :href="state.downloadUrl" :download="state.session.name">保存已校验文件</a>
      </template>
      <el-button v-if="state.active" @click="controller?.cancel()">取消传输</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.transfer-page { display: grid; gap: 16px; max-width: 1080px; margin: 0 auto; }
.transfer-inputs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
h1, h2 { margin: 0; font-size: 18px; }
h2 { font-size: 16px; }
p { overflow-wrap: anywhere; }
input[type=file] { display: block; max-width: 100%; margin: 12px 0; }
.checksum { overflow-wrap: anywhere; }
.pair-code { font-family: monospace; font-size: 22px; letter-spacing: 2px; }
@media (max-width: 640px) { .transfer-inputs { grid-template-columns: 1fr; } }
</style>
