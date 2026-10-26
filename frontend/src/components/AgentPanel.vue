<script setup lang="ts">
import { ref } from 'vue'
import type { Mission } from '../api/types'
import type { CodeExecution } from '../api/codeExecutions'
import type { ExecutionCandidate } from '../api/executions'
import MissionCodePanel from './MissionCodePanel.vue'
import MissionExecutionPanel from './MissionExecutionPanel.vue'
defineProps<{ mission: Mission; canAdopt?: boolean }>()
const emit = defineEmits<{ adoptCode: [execution: CodeExecution]; adoptImages: [candidates: ExecutionCandidate[]] }>()
const kind = ref<'code' | 'image'>('code')
</script>
<template>
  <section aria-label="统一 Agent 面板">
    <el-card shadow="never" class="agent-heading">
      <h3>Agent 委派</h3>
      <p>选择委派类型，预览后交给本地设备执行。模型与凭据由本机管理，成果仍需人工发布、提交和验收。</p>
      <el-radio-group v-model="kind" aria-label="委派类型">
        <el-radio-button value="code">代码实现</el-radio-button>
        <el-radio-button value="image">图像生成/编辑</el-radio-button>
      </el-radio-group>
      <router-link class="app-link" to="/agent-devices">管理本地 Agent 设备</router-link>
    </el-card>
    <MissionCodePanel v-if="kind === 'code'" :key="`code-${mission.id}`" :mission="mission" :can-adopt="canAdopt" @adopt="emit('adoptCode', $event)" />
    <MissionExecutionPanel v-else :key="`image-${mission.id}`" :mission="mission" :can-adopt="canAdopt" @adopt="emit('adoptImages', $event)" />
  </section>
</template>
<style scoped>
.agent-heading { margin-top: 16px; }
.agent-heading .app-link { display: inline-block; margin: 12px; }
</style>
