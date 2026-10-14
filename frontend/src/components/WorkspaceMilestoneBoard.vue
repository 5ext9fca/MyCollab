<script setup lang="ts">
/** F5 view A: milestone x status board. */
import { reactive, ref } from 'vue'

import type { MissionStatus, WorkspaceGroup, WorkspaceNode } from '../api/types'
import { MILESTONE_STATUS_LABELS, MILESTONE_STATUS_TAG } from '../missionMeta'
import WorkspaceMissionCard from './WorkspaceMissionCard.vue'

const props = defineProps<{
  groups: WorkspaceGroup[]
  columns: MissionStatus[]
  columnLabels: Record<MissionStatus, string>
  filtersActive: boolean
  selectedId: string | null
}>()

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
  (event: 'loadMore'): void
}>()

const collapsed = reactive<Record<string, boolean>>({})
const sortBy = ref<'priority' | 'updated'>('priority')

const groupKey = (group: WorkspaceGroup) => group.milestone?.id ?? 'unassigned'

function toggle(key: string) {
  collapsed[key] = !collapsed[key]
}

function cardsFor(group: WorkspaceGroup, status: MissionStatus): WorkspaceNode[] {
  const items = group.columns[status] ?? []
  if (sortBy.value === 'priority') return items
  return [...items].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
}

function progressText(group: WorkspaceGroup): string {
  const { effective_total, done } = group.full_counts
  if (!effective_total) return '暂无有效任务'
  return `${done} / ${effective_total}`
}

function hasMore(group: WorkspaceGroup, status: MissionStatus): boolean {
  return (group.loaded[status] ?? 0) < (group.matched_counts[status] ?? 0)
}
</script>

<template>
  <div class="board">
    <div class="board__sort">
      <span class="meta">卡片排序</span>
      <el-radio-group v-model="sortBy" size="small">
        <el-radio-button value="priority">优先级</el-radio-button>
        <el-radio-button value="updated">更新时间</el-radio-button>
      </el-radio-group>
      <span class="meta">（拖动卡片不会改变状态，认领/验收请用明确操作）</span>
    </div>

    <el-empty v-if="!groups.length" description="还没有里程碑或任务" />

    <section v-for="group in groups" :key="groupKey(group)" class="board__group">
      <header class="board__group-head" @click="toggle(groupKey(group))">
        <span class="board__collapse">{{ collapsed[groupKey(group)] ? '▸' : '▾' }}</span>
        <strong class="board__group-name">
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
        <span v-if="group.milestone?.due_date" class="meta">
          目标 {{ group.milestone.due_date }}
        </span>
        <el-tag v-if="group.milestone?.overdue" type="danger" size="small" disable-transitions>
          已延期
        </el-tag>
        <span class="board__group-spacer" />
        <span class="meta">里程碑总计 {{ progressText(group) }}</span>
        <span v-if="filtersActive" class="meta">
          · 当前筛选 {{ group.matched_total }} 个
        </span>
      </header>

      <div v-show="!collapsed[groupKey(group)]" class="board__columns">
        <div v-for="status in columns" :key="status" class="board__column">
          <div class="board__column-head">
            <span>{{ columnLabels[status] }}</span>
            <span class="meta">
              {{ group.matched_counts[status] ?? 0 }}
            </span>
          </div>
          <div class="board__cards">
            <WorkspaceMissionCard
              v-for="node in cardsFor(group, status)"
              :key="node.id"
              :node="node"
              :selected="node.id === selectedId"
              @select="emit('select', $event)"
              @focus="emit('focus', $event)"
            />
            <el-button
              v-if="hasMore(group, status)"
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
  </div>
</template>

<style scoped>
.board__sort {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.board__group {
  margin-bottom: 20px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
}
.board__group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-wrap: wrap;
}
.board__group-name {
  font-size: 15px;
}
.board__group-spacer {
  flex: 1;
}
.board__collapse {
  color: #94a3b8;
}
.board__columns {
  display: grid;
  grid-template-columns: repeat(5, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 12px;
  overflow-x: auto;
}
.board__column {
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  padding: 8px;
  min-height: 80px;
}
.board__column-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.board__cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.board__cards :deep(.ws-card) {
  width: 100%;
}

@media (max-width: 900px) {
  .board__columns {
    grid-template-columns: 1fr;
  }
}
</style>
