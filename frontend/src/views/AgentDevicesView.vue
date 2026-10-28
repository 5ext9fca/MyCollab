<script setup lang="ts">
import { desktop, type RunnerBindingSummary } from '../platform/desktop'
import { onMounted, ref } from 'vue'
import { createAgentDevice, listAgentDevices, revokeAgentDevice, listAssistance, cancelAssistance } from '../api/agentBridge'
import type { AgentDevice, AssistanceKind, AssistanceSummary } from '../api/agentBridge'
const devices = ref<AgentDevice[]>([])
const requests = ref<AssistanceSummary[]>([])
const page = ref(1)
const count = ref(0)
const name = ref('我的电脑')
const days = ref(30)
const token = ref('')
const localToken = ref('')
const selectedDevice = ref('')
const model = ref('')
const opencode = ref('opencode')
const localBinding = ref<RunnerBindingSummary | null>(null)
const error = ref('')
const busy = ref(false)
const capabilities = ref<AssistanceKind[]>(['design_polish', 'template_generate', 'mission_write', 'review_assist', 'agent_requirements'])
const names: Record<AssistanceKind, string> = { design_polish: '设计/资产说明', template_generate: '生产模板', mission_write: 'Mission 编写', review_assist: '验收辅助', agent_requirements: 'Agent 需求文档' }
async function load() {
  try { const [d, r] = await Promise.all([listAgentDevices(), listAssistance(page.value)]); devices.value = d.results; requests.value = r.results; count.value = r.count }
  catch (err) { error.value = err instanceof Error ? err.message : '加载失败' }
}
async function create() {
  busy.value = true; error.value = ''
  try {
    const created = await createAgentDevice(name.value, capabilities.value, days.value)
    token.value = created.token
    if (desktop) { selectedDevice.value = created.id; localToken.value = created.token }
    await load()
  }
  catch (err) { error.value = err instanceof Error ? err.message : '绑定失败' } finally { busy.value = false }
}
async function revoke(id: string) {
  try { await revokeAgentDevice(id); token.value = ''; if (selectedDevice.value === id) localToken.value = ''; await load() } catch (err) { error.value = err instanceof Error ? err.message : '撤销失败' }
}
async function cancel(id: string) {
  try { await cancelAssistance(id); await load() } catch (err) { error.value = err instanceof Error ? err.message : '取消失败' }
}
async function bindLocal() {
  if (!desktop) return
  busy.value = true; error.value = ''
  try {
    localBinding.value = await desktop.bindRunner({ deviceId: selectedDevice.value, token: localToken.value,
      model: model.value, opencode: opencode.value })
    token.value = ''; localToken.value = ''
  } catch { error.value = '本机绑定失败：请确认设备令牌属于当前账户与所选设备、服务器已更新并且系统钥匙串可用。' }
  finally { busy.value = false }
}
onMounted(async () => {
  await load()
  if (!desktop) return
  try {
    localBinding.value = await desktop.runnerBinding()
    if (localBinding.value) {
      selectedDevice.value = localBinding.value.deviceId
      model.value = localBinding.value.model
      opencode.value = localBinding.value.opencode
    }
  } catch { error.value = '无法读取本机绑定，请检查登录状态及系统凭据保护。' }
})
</script>
<template>
  <div class="page">
    <el-card shadow="never" class="section-card">
      <h2>本地 Agent 设备</h2><p v-if="desktop">在本机安装 OpenCode 并完成模型供应商登录，再创建和绑定设备。供应商凭据不要粘贴到此页面。</p><p v-else>在本人电脑安装 local_runner，配置本地模型环境，再使用下方设备凭据绑定。供应商凭据只在本地配置，不要粘贴到此页面。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-form label-position="top" @submit.prevent="create">
        <el-form-item label="设备名称"><el-input v-model="name" maxlength="100" /></el-form-item>
        <el-form-item label="凭据有效天数"><el-input-number v-model="days" :min="1" :max="90" /></el-form-item>
        <el-checkbox-group v-model="capabilities"><el-checkbox v-for="(label, value) in names" :key="value" :value="value">{{ label }}</el-checkbox></el-checkbox-group>
        <el-button native-type="submit" :loading="busy">创建设备凭据</el-button>
      </el-form>
      <el-card v-if="token" shadow="never"><h3>仅本次展示的设备凭据</h3><p>保存在本机权限为 600 的配置文件中。离开页面后无法找回，可撤销后重新创建。</p><el-input :model-value="token" type="password" show-password readonly aria-label="设备凭据" /><el-button @click="token = ''">隐藏凭据</el-button></el-card>
    </el-card>
    <el-card v-if="desktop" shadow="never" class="section-card">
      <template #header><b>本机 Agent 绑定</b></template>
      <p v-if="localBinding">本机已保存设备配置。已保存的令牌不会回显，保存不会自动启动模型。</p>
      <p>选择当前账户的设备并填写设备令牌；不要填写模型供应商密钥。新创建设备会自动填入本次令牌。</p>
      <el-form label-position="top" @submit.prevent="bindLocal">
        <el-form-item label="设备"><el-select v-model="selectedDevice"><el-option v-for="device in devices"
          :key="device.id" :label="device.name" :value="device.id" :disabled="!!device.revoked_at" /></el-select></el-form-item>
        <el-form-item label="设备令牌"><el-input v-model="localToken" type="password" autocomplete="off" /></el-form-item>
        <el-form-item label="OpenCode 模型"><el-input v-model="model" placeholder="provider/model" /></el-form-item>
        <el-form-item label="OpenCode 可执行文件"><el-input v-model="opencode" /></el-form-item>
        <el-button type="primary" native-type="submit" :loading="busy">验证并加密保存到本机</el-button>
      </el-form>
    </el-card>
    <el-card shadow="never" class="section-card"><h3>已绑定设备</h3><el-button @click="load">刷新</el-button>
      <el-table :data="devices"><el-table-column prop="name" label="名称" /><el-table-column label="最近联系"><template #default="{ row }">{{ row.last_seen_at ? new Date(row.last_seen_at).toLocaleString() : '尚未联系' }}</template></el-table-column><el-table-column label="有效期"><template #default="{ row }">{{ row.revoked_at ? '已撤销' : new Date(row.expires_at).toLocaleString() }}</template></el-table-column><el-table-column label="操作"><template #default="{ row }"><el-button v-if="!row.revoked_at" @click="revoke(row.id)">撤销</el-button></template></el-table-column></el-table>
    </el-card>
    <el-card shadow="never" class="section-card"><h3>辅助请求记录</h3><p>仅本人可见，保留 30 天。取消不保证模型提供商退费；过期请求不会自动重试。</p>
      <el-table :data="requests"><el-table-column label="类型"><template #default="{ row }">{{ names[row.kind as AssistanceKind] }}</template></el-table-column><el-table-column prop="status" label="状态" /><el-table-column prop="error" label="错误" /><el-table-column label="操作"><template #default="{ row }"><el-button v-if="['queued', 'running', 'succeeded'].includes(row.status)" @click="cancel(row.id)">取消/放弃</el-button></template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" :total="count" :page-size="20" layout="prev, pager, next" @current-change="load" />
    </el-card>
  </div>
</template>
