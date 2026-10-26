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
    <el-card class="section-card" shadow="never"><div class="toolbar toolbar--flush"><el-select v-model="filter" style="width: 160px"><el-option label="全部" value="all" /><el-option label="未读" value="unread" /><el-option label="已读" value="read" /></el-select>
    <el-button :disabled="!selected.length || busy" @click="read(selected)">将选中通知标为已读</el-button></div></el-card>
    <el-empty v-if="!rows.length" description="暂无通知" />
    <el-checkbox-group v-model="selected">
      <el-card v-for="row in rows" :key="row.id" class="notification-card" shadow="never" @click="read([row.id], row.mission)">
        <div class="selectable-card-layout">
          <div class="selectable-card-selection" @click.stop>
            <el-checkbox :value="row.id" :aria-label="`选择通知：${row.mission_title}`" />
          </div>
          <div class="selectable-card-content">
            <div class="card-heading">
              <button type="button" class="app-link app-link--title" :disabled="busy" @click.stop="read([row.id], row.mission)">{{ row.mission_title }}</button>
              <el-tag :type="row.read_at ? 'info' : 'primary'" size="small">{{ row.read_at ? '已读' : '未读' }}</el-tag>
            </div>
            <p class="notification-summary">{{ row.payload.summary }}</p>
            <span class="meta">{{ new Date(row.created_at).toLocaleString() }}</span>
          </div>
        </div>
      </el-card>
    </el-checkbox-group>
    <el-pagination :total="total" :current-page="page" :page-size="20" layout="prev, pager, next" @current-change="page = $event; load()" />
    <MissionDetailDrawer :mission-id="target" :open="!!target" @close="target = null" @changed="load(); notifyChanged()" @focus="target = $event" />
  </div>
</template>

<style scoped>
.notification-card { margin-bottom: 16px; cursor: pointer; }
.notification-summary { margin: 8px 0; overflow-wrap: anywhere; }
</style>
