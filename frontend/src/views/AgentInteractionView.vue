<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getMission } from '../api/missions'
import type { Mission } from '../api/types'
import AgentPanel from '../components/AgentPanel.vue'

const props = defineProps<{ id: string }>()
const route = useRoute()
const mission = ref<Mission | null>(null)
const error = ref('')
const loading = ref(false)
const initialKind = computed(() => route.query.kind === 'image' ? 'image' : 'code')
let generation = 0
async function load() {
  const current = ++generation
  mission.value = null; error.value = ''; loading.value = true
  try {
    const result = await getMission(props.id)
    if (current === generation) mission.value = result
  } catch (err) {
    if (current === generation) error.value = err instanceof Error ? err.message : '加载 Mission 失败'
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(() => props.id, load, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <div class="page">
    <el-card shadow="never">
      <h2>Agent 交互</h2>
      <p v-if="mission">{{ mission.title }}</p>
      <p>在此创建委派、查看执行进度、进行私有对话与单次权限审批。成果引用、提交与验收在 Mission 详情完成。</p>
      <router-link class="app-link" :to="`/missions/${id}`">返回 Mission 详情</router-link>
      <el-button :loading="loading" @click="load">刷新 Mission</el-button>
      <p v-if="loading">正在加载 Mission…</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </el-card>
    <AgentPanel v-if="mission" :key="`${mission.id}-${initialKind}`" :mission="mission" :initial-kind="initialKind" />
  </div>
</template>
<style scoped>
.el-button { margin-left: 16px; }
</style>
