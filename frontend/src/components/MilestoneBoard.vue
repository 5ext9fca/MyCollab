<script setup lang="ts">
/**
 * F5 view A: the milestone x status board.
 *
 * Groups come from the server already scoped (milestone totals vs filtered
 * counts); this component only arranges them with CSS Grid. It never merges
 * parent/child missions, and dragging a card cannot change a mission's status.
 */
import { reactive, ref } from 'vue'

import type { MissionStatus, WorkspaceGroup } from '../api/types'
import MilestoneGroup from './MilestoneGroup.vue'

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

    <MilestoneGroup
      v-for="group in groups"
      :key="groupKey(group)"
      :group="group"
      :columns="columns"
      :column-labels="columnLabels"
      :selected-id="selectedId"
      :collapsed="!!collapsed[groupKey(group)]"
      :sort-by="sortBy"
      :filters-active="filtersActive"
      @toggle="toggle(groupKey(group))"
      @select="emit('select', $event)"
      @focus="emit('focus', $event)"
      @load-more="emit('loadMore')"
    />
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
</style>
