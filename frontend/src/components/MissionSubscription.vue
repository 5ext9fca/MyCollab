<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getSubscription, putSubscription, type Subscription } from '../api/notifications'
const props = defineProps<{ missionId: string }>()
const data = ref<Subscription | null>(null)
const busy = ref(false)
const error = ref('')
let generation = 0
async function load() {
  const token = ++generation
  data.value = null
  error.value = ''
  try { const result = await getSubscription(props.missionId); if (token === generation) data.value = result }
  catch { if (token === generation) error.value = '订阅加载失败，可重试；不影响任务操作' }
}
watch(() => props.missionId, load, { immediate: true })
async function change(mode: 'Follow' | 'Mute') {
  if (!data.value || busy.value) return
  busy.value = true
  const id = props.missionId
  try {
    const result = await putSubscription(id, mode, data.value.subscription?.version ?? 0)
    if (id === props.missionId) data.value = result
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '订阅操作失败'); await load() }
  finally { busy.value = false }
}
</script>
<template>
  <div class="meta">
    <template v-if="data">
      <span>{{ data.effective_following ? '已关注' : '未关注普通动态' }}</span>
      <el-button link :disabled="busy" @click="change('Follow')">关注</el-button>
      <el-button link :disabled="busy" @click="change('Mute')">静音普通动态</el-button>
      <p>静音普通动态，职责提醒仍保留。</p>
    </template>
    <el-button v-if="error" link @click="load">{{ error }}</el-button>
  </div>
</template>
