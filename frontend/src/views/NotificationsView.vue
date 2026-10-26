<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotifications, readNotifications, notifyChanged, type Notification } from '../api/notifications'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
const rows = ref<Notification[]>([]), selected = ref<string[]>([])
const pageSize = ref(20), ordering = ref('-created_at')
const filter = ref('all'), page = ref(1), total = ref(0), busy = ref(false), target = ref<string | null>(null)
let generation = 0
async function load() {
  const token = ++generation
  selected.value = []; rows.value = []
  try { const result = await listNotifications({ read: filter.value, page: page.value, page_size: pageSize.value, ordering: ordering.value }); if (token === generation) { rows.value = result.results; total.value = result.count } }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '通知加载失败') }
}
async function read(ids: string[], mission?: string) {
  if (busy.value) return
  busy.value = true
  try { await readNotifications(ids); notifyChanged(); await load(); if (mission) target.value = mission }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '标记已读失败') }
  finally { busy.value = false }
}
watch([filter, ordering, pageSize], () => { page.value = 1; void load() })
onMounted(load)
onUnmounted(() => { generation++ })
</script>
<template>
  <div class="page"><h2>站内通知</h2>
    <el-card class="section-card" shadow="never"><div class="toolbar toolbar--flush"><el-select v-model="filter" style="width: 160px"><el-option label="全部" value="all" /><el-option label="未读" value="unread" /><el-option label="已读" value="read" /></el-select>
    <el-select v-model="ordering" aria-label="通知排序" style="width: 160px"><el-option label="最新通知" value="-created_at" /><el-option label="最早通知" value="created_at" /></el-select>
    <el-checkbox :model-value="rows.length > 0 && selected.length === rows.length" :indeterminate="selected.length > 0 && selected.length < rows.length" :disabled="busy || !rows.length" @change="selected = $event ? rows.map(row => row.id) : []">本页全选</el-checkbox>
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
    <el-pagination class="list-pagination" :total="total" :current-page="page" :page-size="pageSize" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @size-change="pageSize = $event" @current-change="page = $event; load()" />
    <MissionDetailDrawer :mission-id="target" :open="!!target" @close="target = null" @changed="load(); notifyChanged()" @focus="target = $event" />
  </div>
</template>

<style scoped>
.notification-card { margin-bottom: 16px; cursor: pointer; }
.notification-summary { margin: 8px 0; overflow-wrap: anywhere; }
</style>
