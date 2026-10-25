<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotifications, readNotifications, notifyChanged, type Notification } from '../api/notifications'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
const rows = ref<Notification[]>([]), selected = ref<string[]>([])
const filter = ref('all'), page = ref(1), total = ref(0), busy = ref(false), target = ref<string | null>(null)
let generation = 0
async function load() {
  const token = ++generation
  selected.value = []
  try { const result = await listNotifications({ read: filter.value, page: page.value }); if (token === generation) { rows.value = result.results; total.value = result.count } }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '通知加载失败') }
}
async function read(ids: string[], mission?: string) {
  if (busy.value) return
  busy.value = true
  try { await readNotifications(ids); notifyChanged(); await load(); if (mission) target.value = mission }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '标记已读失败') }
  finally { busy.value = false }
}
watch(filter, () => { page.value = 1; void load() })
onMounted(load)
onUnmounted(() => { generation++ })
</script>
<template>
  <div class="page"><h2>站内通知</h2>
    <div class="toolbar"><el-select v-model="filter" style="width: 160px"><el-option label="全部" value="all" /><el-option label="未读" value="unread" /><el-option label="已读" value="read" /></el-select>
    <el-button :disabled="!selected.length || busy" @click="read(selected)">将选中通知标为已读</el-button></div>
    <el-empty v-if="!rows.length" description="暂无通知" />
    <el-checkbox-group v-model="selected">
      <div v-for="row in rows" :key="row.id" class="toolbar">
        <el-checkbox :value="row.id" :label="row.id"><span class="sr-only">选择通知</span></el-checkbox>
        <el-button link :disabled="busy" @click="read([row.id], row.mission)">{{ row.read_at ? '已读' : '未读' }} · {{ row.mission_title }} · {{ row.payload.summary }}</el-button>
        <span class="meta">{{ new Date(row.created_at).toLocaleString() }}</span>
      </div>
    </el-checkbox-group>
    <el-pagination :total="total" :current-page="page" :page-size="20" layout="prev, pager, next" @current-change="page = $event; load()" />
    <MissionDetailDrawer :mission-id="target" :open="!!target" @close="target = null" @changed="load(); notifyChanged()" @focus="target = $event" />
  </div>
</template>
