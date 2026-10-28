<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { desktop, type DesktopSettings } from '../platform/desktop'

const settings = ref<DesktopSettings>()
const server = ref('')
const busy = ref(false)
const error = ref('')
onMounted(async () => {
  try {
    settings.value = await desktop?.settings()
    server.value = settings.value?.server || ''
  } catch { error.value = '无法读取桌面设置。' }
})
async function saveServer() {
  if (!desktop) return
  busy.value = true
  error.value = ''
  try { await desktop.setServer(server.value) }
  catch { error.value = '连接设置失败。请填写 HTTPS 根地址；本机开发地址可使用 HTTP。' }
  finally { busy.value = false }
}
async function localNetwork(value: string | number | boolean) {
  if (!desktop || !settings.value) return
  busy.value = true
  try { settings.value.localNetwork = await desktop.setLocalNetwork(Boolean(value)) }
  catch { error.value = '无法修改局域网权限。' }
  finally { busy.value = false }
}
async function autostart(value: string | number | boolean) {
  if (!desktop || !settings.value) return
  busy.value = true
  try { settings.value.autostart = await desktop.setAutostart(Boolean(value)) }
  catch { error.value = '无法修改开机启动设置。' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="desktop-settings">
    <el-card shadow="never">
      <template #header><b>桌面设置</b></template>
      <template v-if="desktop">
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
        <el-form label-position="top" @submit.prevent="saveServer">
          <el-form-item label="协作服务器">
            <el-input v-model="server" placeholder="https://collab.example.com" :disabled="busy" />
          </el-form-item>
          <p class="meta">切换服务器将退出当前登录并重新加载页面。请先保存编辑内容、结束文件传输。</p>
          <el-button type="primary" native-type="submit" :loading="busy">保存服务器并前往登录</el-button>
        </el-form>
        <el-divider />
        <el-form-item label="局域网文件直传">
          <el-switch v-if="settings" :model-value="settings.localNetwork" :disabled="busy"
            active-text="允许客户端访问局域网" @change="localNetwork" />
        </el-form-item>
        <p class="meta">文件直传需双方打开传输页面，并允许系统的局域网访问。更改此权限后请重新进入传输页面。</p>
        <el-switch v-if="settings" :model-value="settings.autostart" :disabled="busy"
          active-text="登录系统后启动 MyCollab" @change="autostart" />
        <p class="meta">关闭窗口会隐藏到托盘；在托盘菜单中选择“退出”以关闭客户端。</p>
      </template>
      <el-alert v-else title="此页面仅在 MyCollab 桌面客户端提供本地设置。" type="info" :closable="false" />
    </el-card>
    <el-card v-if="settings" shadow="never">
      <template #header><b>客户端信息</b></template>
      <el-descriptions :column="1">
        <el-descriptions-item label="版本">{{ settings.version }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ settings.platform }} · {{ settings.arch }}</el-descriptions-item>
        <el-descriptions-item label="Electron">{{ settings.electron }}</el-descriptions-item>
        <el-descriptions-item label="Chromium">{{ settings.chromium }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
    <router-link class="app-link app-link--action" to="/">返回协作页面</router-link>
  </div>
</template>

<style scoped>
.desktop-settings { max-width: 720px; margin: 32px auto; padding: 0 16px; display: grid; gap: 16px; }
</style>
