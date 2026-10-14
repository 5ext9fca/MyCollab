<script setup lang="ts">
/** F5 view A: one milestone group inside the board (header + status columns). */
import type { MissionStatus, WorkspaceGroup, WorkspaceNode } from '../api/types'
import { MILESTONE_STATUS_LABELS, MILESTONE_STATUS_TAG } from '../missionMeta'
import WorkspaceMissionCard from './WorkspaceMissionCard.vue'

const props = defineProps<{
  group: WorkspaceGroup
  columns: MissionStatus[]
  columnLabels: Record<MissionStatus, string>
  selectedId: string | null
  collapsed: boolean
  sortBy: 'priority' | 'updated'
  filtersActive: boolean
}>()

const emit = defineEmits<{
  (event: 'toggle'): void
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
  (event: 'loadMore'): void
}>()

function cardsFor(status: MissionStatus): WorkspaceNode[] {
  const items = props.group.columns[status] ?? []
  if (props.sortBy === 'priority') return items
  return [...items].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
}

function progressText(): string {
  const { effective_total, done } = props.group.full_counts
  if (!effective_total) return '暂无有效任务'
  return `${done} / ${effective_total}`
}

function hasMore(status: MissionStatus): boolean {
  return (props.group.loaded[status] ?? 0) < (props.group.matched_counts[status] ?? 0)
}
</script>

<template>
  <section class="group">
    <header class="group__head" @click="emit('toggle')">
      <span class="group__collapse">{{ collapsed ? '▸' : '▾' }}</span>
      <strong class="group__name">
        {{ group.is_unassigned ? '未归属里程碑' : group.milestone?.name }}
      </strong>
      <el-tag
        v-if="group.milestone"
        size="small"
        :type="MILESTONE_STATUS_TAG[group.milestone.status]"
        disable-transitions
      >
        {{ MILESTONE_STATUS_LABELS[group.milestone.status] }}
      </el-tag>
      <span v-if="group.milestone?.due_date" class="meta">目标 {{ group.milestone.due_date }}</span>
      <el-tag v-if="group.milestone?.overdue" type="danger" size="small" disable-transitions>
        已延期
      </el-tag>
      <span class="group__spacer" />
      <span class="meta" title="该里程碑全部可见任务的完成比例">里程碑总计 {{ progressText() }}</span>
      <span v-if="filtersActive" class="meta">· 当前筛选 {{ group.matched_total }} 个</span>
    </header>

    <div v-show="!collapsed" class="group__columns">
      <div v-for="status in columns" :key="status" class="group__column">
        <div class="group__column-head">
          <span>{{ columnLabels[status] }}</span>
          <span class="meta">{{ group.matched_counts[status] ?? 0 }}</span>
        </div>
        <div class="group__cards">
          <WorkspaceMissionCard
            v-for="node in cardsFor(status)"
            :key="node.id"
            :node="node"
            :selected="node.id === selectedId"
            @select="emit('select', $event)"
            @focus="emit('focus', $event)"
          />
          <el-button
            v-if="hasMore(status)"
            link
            type="primary"
            size="small"
            @click="emit('loadMore')"
          >
            加载更多（已显示 {{ group.loaded[status] }} / {{ group.matched_counts[status] }}）
          </el-button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.group {
  margin-bottom: 20px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
}
.group__head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-wrap: wrap;
}
.group__name {
  font-size: 15px;
}
.group__spacer {
  flex: 1;
}
.group__collapse {
  color: #94a3b8;
}
.group__columns {
  display: grid;
  grid-template-columns: repeat(5, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 12px;
  overflow-x: auto;
}
.group__column {
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  padding: 8px;
  min-height: 80px;
}
.group__column-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.group__cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.group__cards :deep(.ws-card) {
  width: 100%;
}

@media (max-width: 900px) {
  .group__columns {
    grid-template-columns: 1fr;
  }
}
</style>
