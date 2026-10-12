<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => {
  if (route.name === 'claimed') return '/claimed'
  if (route.name === 'published') return '/published'
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
        <el-menu-item index="/missions">任务广场</el-menu-item>
        <el-menu-item index="/claimed">我认领的</el-menu-item>
        <el-menu-item index="/published">我发布的</el-menu-item>
        <el-menu-item index="/library">素材库</el-menu-item>
        <el-menu-item v-if="auth.user?.is_staff" index="/manage">管理后台</el-menu-item>
      </el-menu>
      <div class="app-header__user">
        <span class="meta">{{ auth.user?.display_name }}</span>
        <el-button link type="primary" @click="onLogout">退出</el-button>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.app-header__brand {
  font-weight: 700;
  font-size: 16px;
  white-space: nowrap;
}
.app-header__menu {
  flex: 1;
  border-bottom: none;
}
.app-header__user {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
</style>
