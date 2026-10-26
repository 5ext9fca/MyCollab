<script setup lang="ts">
import CardListSort from '../components/CardListSort.vue'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotifications, readNotifications, notifyChanged } from '../api/notifications'
import ActionCardList from '../components/ActionCardList.vue'
import CardListSelection from '../components/CardListSelection.vue'
import { useCardList } from '../composables/useCardList'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
const selected = ref<string[]>([]), ordering = ref('-created_at'), filter = ref('all')
const busy = ref(false), target = ref<string | null>(null)
const { items: rows, total, loading, page, pageSize, resetKey, reload: load } = useCardList(() => ({ read: filter.value, ordering: ordering.value }), listNotifications)
async function read(ids: string[], mission?: string) {
  if (busy.value) return
  busy.value = true
  try { await readNotifications(ids); selected.value = []; notifyChanged(); await load(); if (mission) target.value = mission }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '标记已读失败') }
  finally { busy.value = false }
}
</script>
<template>
  <div class="page"><h2>站内通知</h2>
    <ActionCardList :items="rows" :total="total" :loading="loading" v-model:page="page" v-model:page-size="pageSize" v-model:selected-ids="selected" :reset-key="resetKey" :busy="busy" empty-text="暂无通知">
    <template #filters><div class="toolbar toolbar--flush"><el-select v-model="filter" style="width: 160px"><el-option label="全部" value="all" /><el-option label="未读" value="unread" /><el-option label="已读" value="read" /></el-select>
    <CardListSort v-model="ordering" label="通知排序" :options="[{ label: '最新通知', value: '-created_at' }, { label: '最早通知', value: 'created_at' }]" />
    </div></template>
    <template #actions="{ disabled }">
    <el-button :disabled="disabled" @click="read(selected)">将选中通知标为已读</el-button></template>
    <template #item="{ item: row }">
      <el-card class="notification-card" shadow="never" @click="read([row.id], row.mission)">
        <div class="selectable-card-layout">
          <CardListSelection :id="row.id" :label="`选择通知：${row.mission_title}`" />
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
    </template>
    </ActionCardList>
    <MissionDetailDrawer :mission-id="target" :open="!!target" @close="target = null" @changed="load(); notifyChanged()" @focus="target = $event" />
  </div>
</template>

<style scoped>
.notification-card { margin-bottom: 16px; cursor: pointer; }
.notification-summary { margin: 8px 0; overflow-wrap: anywhere; }
</style>
