<script setup lang="ts">
import type { ScheduleFields } from '../api/types'
defineProps<{ mission: ScheduleFields }>()
</script>
<template>
  <div class="schedule-info">
    <span>计划：{{ mission.planned_start_date ?? '未设开始' }} → {{ mission.planned_end_date ?? '未设结束' }}</span>
    <el-tag v-if="mission.overdue" type="danger" size="small">逾期</el-tag>
    <el-tag v-if="mission.dependency_date_conflict_ids?.length" type="warning" size="small">{{ mission.dependency_date_conflict_ids.length }} 项前置日期冲突</el-tag>
    <el-tag v-if="mission.beyond_milestone_due" type="warning" size="small">超出里程碑目标日期</el-tag>
  </div>
</template>
<style scoped>.schedule-info { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 8px 0; color: var(--el-text-color-regular); }</style>
