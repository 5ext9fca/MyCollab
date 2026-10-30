<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, type Status } from './bridge'
const form = reactive({ server: '', device_token: '', model: '', opencode: '', ca_file: '' })
const tokenPresent = ref(false), autostart = ref(false), busy = ref(false), message = ref(''), error = ref('')
const status = ref<Status>({ running: false, exit_code: null, detail: {}, configured: false })
const checks = ref<Record<string, unknown> | null>(null)
const stateNames: Record<string, string> = { starting: '正在启动', running: '正在生成', delivering: '正在回传', idle: '等待请求', offline: '连接中断，等待恢复', stopped: '已停止', unauthorized: '凭据已失效' }
const stateLabel = computed(() => status.value.running ? (stateNames[status.value.detail.state ?? ''] ?? '运行中') : '已停止')
async function act(action: () => Promise<unknown>, success = '') {
  busy.value = true; error.value = ''; message.value = ''
  try { await action(); if (success) message.value = success; await refresh() }
  catch (e) { error.value = String(e) }
  finally { busy.value = false }
}
async function refresh() { status.value = await api.status() }
async function save() {
  await act(async () => { await api.save({ ...form }); form.device_token = ''; tokenPresent.value = true }, '配置已保存。请先自检，再启动。')
}
async function update() { await act(async () => { message.value = await api.update() }) }
async function diagnose() { await act(async () => { checks.value = await api.diagnose() }) }
async function toggleAutostart(value: string | number | boolean) {
  await act(async () => { await api.autostart(Boolean(value)); autostart.value = Boolean(value) }, '已更新登录启动偏好。')
}
let timer: ReturnType<typeof setInterval> | undefined
let polling = false
onMounted(async () => {
  await act(async () => {
    const config = await api.config()
    form.server = config.server; form.model = config.model; form.opencode = config.opencode; form.ca_file = config.ca_file
    tokenPresent.value = config.token_present; autostart.value = config.autostart
  })
  timer = setInterval(async () => {
    if (polling || busy.value) return
    polling = true
    try { await refresh() } catch (e) { error.value = String(e) } finally { polling = false }
  }, 2500)
})
onUnmounted(() => clearInterval(timer))
const checkLabels: Record<string, string> = { ok: '正常', unavailable: '不可用，请检查网络或安装', incompatible: '版本不兼容', unauthorized: '凭据无效或已过期' }
</script>
<template>
  <main>
    <el-card shadow="never" class="intro">
      <h1>MyCollab 本地伴侣</h1>
      <p>在本机管理 Agent 连接，任务协作继续使用浏览器。关闭窗口后留在菜单栏；从菜单栏退出会停止 Runner。</p>
    </el-card>
    <el-card v-if="error || message" shadow="never" aria-live="polite">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-alert v-else :title="message" type="success" :closable="false" />
    </el-card>
    <el-card shadow="never">
      <template #header><strong>连接与模型</strong></template>
      <el-form label-position="top" :disabled="busy || status.running" @submit.prevent="save">
        <el-form-item label="网站地址"><el-input v-model="form.server" placeholder="https://你的团队网站" /></el-form-item>
        <el-form-item label="设备凭据"><el-input v-model="form.device_token" type="password" autocomplete="off" :placeholder="tokenPresent ? '已保存；留空保留，切换网站需重新填写' : '从网站「本地 Agent」复制设备凭据'" /></el-form-item>
        <el-form-item label="模型"><el-input v-model="form.model" placeholder="供应商/模型名称" /></el-form-item>
        <el-form-item label="OpenCode 可执行文件"><el-input v-model="form.opencode" placeholder="例如 /opt/homebrew/bin/opencode" /></el-form-item>
        <el-form-item label="内部 CA 证书（可选 PEM 文件路径）"><el-input v-model="form.ca_file" placeholder="使用内部 HTTPS 证书时填写；公共证书留空" /></el-form-item>
        <p>首次使用需安装 OpenCode 2.1.3，并在终端完成 <code>opencode auth login</code>。用 <code>opencode models --standalone</code> 查看模型名称。供应商凭据由 OpenCode 管理。</p>
        <el-button native-type="submit" type="primary" :loading="busy">保存配置</el-button>
      </el-form>
    </el-card>
    <el-card shadow="never">
      <template #header><strong>运行与恢复</strong></template>
      <div class="actions">
        <el-tag :type="status.running ? 'success' : 'info'">{{ stateLabel }}</el-tag>
        <el-button :disabled="busy || !status.configured || status.running" @click="act(api.start, 'Runner 已启动')">启动</el-button>
        <el-button :disabled="busy || !status.running" @click="act(api.stop, 'Runner 已停止；已保存结果将在下次启动时继续回传')">停止</el-button>
        <el-button :disabled="busy || !status.configured" @click="diagnose">连接自检</el-button>
      </div>
      <p>待回传 {{ status.detail.pending_results ?? 0 }} 项 · 已拒收 {{ status.detail.rejected_results ?? 0 }} 项</p>
      <p v-if="status.exit_code !== null && status.exit_code !== 0">Runner 退出码：{{ status.exit_code }}。请运行自检；不会自动重新执行模型。</p>
      <p>断线重连只回传同一次生成结果；服务端取消或过期后不会覆盖任务。拒收结果在本机保留最多 24 小时。运行中修改连接前请先停止。</p>
      <el-switch :model-value="autostart" :disabled="busy" active-text="登录电脑时启动伴侣和 Runner" @change="toggleAutostart" />
    </el-card>
    <el-card v-if="checks" shadow="never">
      <template #header><strong>诊断结果</strong></template>
      <p>本机 CLI：{{ checkLabels[String(checks.opencode)] ?? checks.opencode }}</p>
      <p>服务器与设备：{{ checkLabels[String(checks.server)] ?? checks.server }}</p>
      <p>协议版本：{{ checks.protocol }}。自检不调用模型，不验证供应商额度；实际登录或额度错误会在执行时提示。</p>
    </el-card>
    <el-card shadow="never">
      <template #header><strong>网站与更新</strong></template>
      <div class="actions">
        <el-button :disabled="busy || !status.configured" @click="act(api.open)">在浏览器打开网站</el-button>
        <el-button :disabled="busy || status.running" @click="update">检查并安装签名更新</el-button>
      </div>
      <p>模型输入可能发送给你选择的供应商并产生费用。网站页面不能直接执行本机命令。</p>
    </el-card>
  </main>
</template>
