<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { createAgentDevice, listAgentDevices, revokeAgentDevice, listAssistance, cancelAssistance } from '../api/agentBridge'
import type { AgentDevice, AgentCapability, AssistanceSummary } from '../api/agentBridge'
const devices = ref<AgentDevice[]>([])
const requests = ref<AssistanceSummary[]>([])
const page = ref(1)
const count = ref(0)
const name = ref('我的电脑')
const days = ref(30)
const token = ref('')
const error = ref('')
const busy = ref(false)
const capabilities = ref<AgentCapability[]>(['design_polish', 'template_generate', 'mission_write', 'review_assist'])
const names: Record<AgentCapability, string> = { design_polish: '设计/资产说明', template_generate: '生产模板', mission_write: 'Mission 编写', review_assist: '验收辅助', image_generate: '图像生成（Codex CLI）', image_edit: '图像编辑（Codex CLI）', code_implement: '代码实现（OpenCode）' }
async function load() {
  try { const [d, r] = await Promise.all([listAgentDevices(), listAssistance(page.value)]); devices.value = d.results; requests.value = r.results; count.value = r.count }
  catch (err) { error.value = err instanceof Error ? err.message : '加载失败' }
}
async function create() {
  busy.value = true; error.value = ''
  try { token.value = (await createAgentDevice(name.value, capabilities.value, days.value)).token; await load() }
  catch (err) { error.value = err instanceof Error ? err.message : '绑定失败' } finally { busy.value = false }
}
async function revoke(id: string) {
  try { await revokeAgentDevice(id); token.value = ''; await load() } catch (err) { error.value = err instanceof Error ? err.message : '撤销失败' }
}
async function cancel(id: string) {
  try { await cancelAssistance(id); await load() } catch (err) { error.value = err instanceof Error ? err.message : '取消失败' }
}
onMounted(load)
</script>
<template>
  <div class="page">
    <el-card shadow="never" class="section-card">
      <h2>本地 Agent 设备</h2><p>在本人电脑安装 local_runner，配置本地模型环境，再使用下方设备凭据绑定。供应商凭据只在本地配置，不要粘贴到此页面。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-form label-position="top" @submit.prevent="create">
        <el-form-item label="设备名称"><el-input v-model="name" maxlength="100" /></el-form-item>
        <el-form-item label="凭据有效天数"><el-input-number v-model="days" :min="1" :max="90" /></el-form-item>
        <el-checkbox-group v-model="capabilities"><el-checkbox v-for="(label, value) in names" :key="value" :value="value">{{ label }}</el-checkbox></el-checkbox-group>
        <el-button native-type="submit" :loading="busy">创建设备凭据</el-button>
      </el-form>
      <el-card v-if="token" shadow="never"><h3>仅本次展示的设备凭据</h3><p>保存在本机权限为 600 的配置文件中。离开页面后无法找回，可撤销后重新创建。</p><el-input :model-value="token" type="password" show-password readonly aria-label="设备凭据" /><el-button @click="token = ''">隐藏凭据</el-button></el-card>
    </el-card>
    <el-card shadow="never" class="section-card"><h3>已绑定设备</h3><el-button @click="load">刷新</el-button>
      <el-table :data="devices"><el-table-column prop="name" label="名称" /><el-table-column label="最近联系"><template #default="{ row }">{{ row.last_seen_at ? new Date(row.last_seen_at).toLocaleString() : '尚未联系' }}</template></el-table-column><el-table-column label="有效期"><template #default="{ row }">{{ row.revoked_at ? '已撤销' : new Date(row.expires_at).toLocaleString() }}</template></el-table-column><el-table-column label="操作"><template #default="{ row }"><el-button v-if="!row.revoked_at" @click="revoke(row.id)">撤销</el-button></template></el-table-column></el-table>
    </el-card>
    <el-card shadow="never" class="section-card"><h3>辅助请求记录</h3><p>仅本人可见。文本请求保留 30 天；图像执行与成果历史保留在 Mission。取消不保证模型提供商退费；过期请求不会自动重试。</p>
      <el-table :data="requests"><el-table-column label="类型"><template #default="{ row }">{{ names[row.kind as AgentCapability] }}</template></el-table-column><el-table-column prop="status" label="状态" /><el-table-column prop="error" label="错误" /><el-table-column label="操作"><template #default="{ row }"><el-button v-if="['queued', 'running', 'awaiting_selection', 'succeeded'].includes(row.status)" @click="cancel(row.id)">取消/放弃</el-button></template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" :total="count" :page-size="20" layout="prev, pager, next" @current-change="load" />
    </el-card>
  </div>
</template>
