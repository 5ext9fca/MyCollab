<script setup lang="ts">
import ThemeSelect from '../components/ThemeSelect.vue'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { register } from '../api/auth'
import { ApiException, ensureCsrf } from '../api/client'

const router = useRouter()

const form = reactive({
  username: '',
  display_name: '',
  email: '',
  password: '',
  confirm: '',
  message: '',
})
const loading = ref(false)
const error = ref('')

onMounted(() => {
  ensureCsrf().catch(() => undefined)
})

async function onSubmit() {
  error.value = ''
  if (form.password !== form.confirm) {
    error.value = '两次输入的密码不一致。'
    return
  }
  loading.value = true
  try {
    await register({
      username: form.username,
      password: form.password,
      email: form.email,
      display_name: form.display_name,
      message: form.message,
    })
    ElMessage.success('申请已提交，请等待管理员审批。')
    await router.push({ name: 'login' })
  } catch (e) {
    error.value = e instanceof ApiException ? e.message : '提交失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card register-card">
      <template #header><b>申请加入 Mission 协作</b></template>
      <div class="auth-theme"><ThemeSelect /></div>
      <el-form label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="姓名（可选）">
          <el-input v-model="form.display_name" />
        </el-form-item>
        <el-form-item label="邮箱（可选）">
          <el-input v-model="form.email" type="email" autocomplete="email" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input
            v-model="form.confirm"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="申请说明（可选）">
          <el-input v-model="form.message" type="textarea" :rows="2" />
        </el-form-item>
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
          提交申请
        </el-button>
      </el-form>
      <div class="login-footer">
        <span>已有账号？</span>
        <router-link class="app-link app-link--action" :to="{ name: 'login' }">去登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.register-card {
  width: 420px;
  max-height: 90vh;
  overflow: auto;
}
</style>
