<script setup lang="ts">
import ThemeSelect from './ThemeSelect.vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

import { notificationSummary } from '../api/notifications'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const unread = ref(0)
let generation = 0
async function refreshNotifications() {
  const token = ++generation
  if (!auth.user || document.hidden) return
  try { const result = await notificationSummary(); if (token === generation) unread.value = result.unread_count } catch { /* 通知失败不阻断页面。 */ }
}
watch(() => auth.user?.id, () => { generation++; unread.value = 0; void refreshNotifications() })
let timer: ReturnType<typeof setInterval>
onMounted(() => { void refreshNotifications(); timer = setInterval(refreshNotifications, 60000); window.addEventListener('notifications-changed', refreshNotifications); window.addEventListener('focus', refreshNotifications) })
onUnmounted(() => { generation++; clearInterval(timer); window.removeEventListener('notifications-changed', refreshNotifications); window.removeEventListener('focus', refreshNotifications) })
const activeMenu = computed(() => {
  if (route.name === 'my-work') return '/my-work'
  if (route.name === 'notifications') return '/notifications'
  if (route.name === 'design' || route.name === 'production-templates') return '/design'
  if (route.name === 'workspace') return '/workspace'
  if (route.name === 'claimed') return '/claimed'
  if (route.name === 'published') return '/published'
  if (route.name === 'milestones' || route.name === 'milestone-detail') return '/milestones'
  if (route.name === 'agent-devices') return '/agent-devices'
  if (route.name === 'file-transfer') return '/file-transfer'
  if (route.name === 'library') return '/library'
  if (route.name === 'manage') return '/manage'
  return '/missions'
})

async function onLogout() {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <el-container>
    <el-header class="app-header">
      <div class="app-header__brand">Mission 协作</div>
      <el-menu
        mode="horizontal"
        :default-active="activeMenu"
        router
        :ellipsis="false"
        class="app-header__menu"
      >
        <el-menu-item index="/my-work">我的工作</el-menu-item>
        <el-menu-item index="/notifications">通知 {{ unread || '' }}</el-menu-item>
        <el-menu-item index="/missions">任务广场</el-menu-item>
        <el-menu-item index="/design">设计与资产</el-menu-item>
        <el-menu-item index="/workspace">工作台</el-menu-item>
        <el-menu-item index="/claimed">我认领的</el-menu-item>
        <el-menu-item index="/published">我发布的</el-menu-item>
        <el-menu-item index="/milestones">里程碑</el-menu-item>
        <el-menu-item index="/file-transfer">文件互传</el-menu-item>
        <el-menu-item index="/library">素材库</el-menu-item>
        <el-menu-item index="/agent-devices">本地 Agent</el-menu-item>
        <el-menu-item v-if="auth.user?.is_staff" index="/manage">管理后台</el-menu-item>
      </el-menu>
      <div class="app-header__user">
        <ThemeSelect />
        <span class="meta">{{ auth.user?.display_name }}</span>
        <el-button class="app-link app-link--action" link type="primary" @click="onLogout">退出</el-button>
      </div>
    </el-header>
    <el-main>
      <router-view :key="`${auth.user?.id}:${String(route.name)}:${JSON.stringify(route.params)}`" />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  height: auto;
  min-height: var(--el-header-height);
  flex-wrap: wrap;
  padding-top: 8px;
  padding-bottom: 8px;
  gap: 8px 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
}
.app-header__brand {
  font-weight: 700;
  font-size: 16px;
  white-space: nowrap;
}
.app-header__menu {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  border-bottom: none;
}
.app-header__user {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .app-header__menu { order: 3; flex-basis: 100%; }
  .app-header__user { margin-left: auto; flex-wrap: wrap; }
}
</style>
