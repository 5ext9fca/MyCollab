<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import { createMission } from '../api/missions'
import type { MissionWritePayload } from '../api/types'
import MissionForm from '../components/MissionForm.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)

async function onSubmit(payload: MissionWritePayload) {
  loading.value = true
  try {
    const parent = typeof route.query.parent === 'string' ? route.query.parent : undefined
    const mission = await createMission({ ...payload, parent })
    ElMessage.success('任务已发布')
    await router.push({ name: 'mission-detail', params: { id: mission.id } })
  } catch (error) {
    if (error instanceof ApiException) {
      const fieldMessages = Object.values(error.fieldErrors).flat().join('；')
      ElMessage.error(fieldMessages || error.message)
    } else {
      ElMessage.error('发布失败')
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>发布任务</h2>
    </div>
    <el-card>
      <MissionForm submit-label="发布" :loading="loading" @submit="onSubmit" />
    </el-card>
  </div>
</template>
