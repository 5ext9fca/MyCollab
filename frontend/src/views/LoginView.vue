<script setup lang="ts">
import ThemeSelect from '../components/ThemeSelect.vue'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException, ensureCsrf } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

onMounted(() => {
  ensureCsrf().catch(() => undefined)
})

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : undefined
    await router.push(redirect ?? { name: 'my-work' })
  } catch (e) {
    error.value = e instanceof ApiException ? e.message : '登录失败，请稍后重试。'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header><b>Mission 协作 · 登录</b></template>
      <div class="auth-theme"><ThemeSelect /></div>
      <el-form label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
          登录
        </el-button>
      </el-form>
      <div class="login-footer">
        <span>还没有账号？</span>
        <el-button link type="primary" @click="router.push({ name: 'register' })">
          申请注册
        </el-button>
      </div>
    </el-card>
  </div>
</template>
