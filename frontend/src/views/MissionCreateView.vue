<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import { createMission, getMission } from '../api/missions'
import type { MissionFormValues } from '../api/types'
import MissionForm from '../components/MissionForm.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const ready = ref(false)
const initial = ref<Partial<MissionFormValues>>({})
onMounted(async () => {
  try {
    if (typeof route.query.design_element === 'string') initial.value.design_element_id = route.query.design_element
    if (typeof route.query.asset === 'string') initial.value.asset_ids = [route.query.asset]
    if (typeof route.query.parent === 'string') {
      const parent = await getMission(route.query.parent)
      initial.value.design_element_id ??= parent.design_element?.id ?? null
      initial.value.asset_ids ??= parent.assets?.map(asset => asset.id) ?? []
    }
  } catch { ElMessage.error('加载父任务设计依据失败，可手动选择') }
  finally { ready.value = true }
})

async function onSubmit(values: MissionFormValues) {
  loading.value = true
  try {
    const parent = typeof route.query.parent === 'string' ? route.query.parent : undefined
    const mission = await createMission({ ...values, parent })
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
      <MissionForm v-if="ready" :initial="initial" submit-label="发布" :loading="loading" @submit="onSubmit" />
    </el-card>
  </div>
</template>
