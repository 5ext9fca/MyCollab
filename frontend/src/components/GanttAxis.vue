<script setup lang="ts">
import { computed } from 'vue'
import { dayNumber, GANTT_ORIGIN, isoDay } from '../composables/useGanttLayout'
import type { WorkspaceNode } from '../api/types'
const props = defineProps<{ data: { from: string; to: string; today: string; scale: number; width: number; height: number; zoom: 'day' | 'week'; nodes: WorkspaceNode[]; undatedY: number | null } }>()
const ticks = computed(() => {
  const start = dayNumber(props.data.from), count = dayNumber(props.data.to) - start + 1
  const step = props.data.zoom === 'day' ? 1 : 7
  return Array.from({ length: Math.ceil(count / step) }, (_, i) => ({ date: isoDay(start + i * step), x: GANTT_ORIGIN + i * step * props.data.scale }))
})
const x = (date: string) => GANTT_ORIGIN + (dayNumber(date) - dayNumber(props.data.from)) * props.data.scale
const inRange = (date: string) => date >= props.data.from && date <= props.data.to
const milestones = computed(() => [...new Map(props.data.nodes.filter(n => n.milestone_id && n.milestone_due_date).map(n => [n.milestone_id, { id: n.milestone_id!, date: n.milestone_due_date!, name: n.milestone_name }])).values()].filter(m => inRange(m.date)))
</script>
<template>
  <svg :width="data.width + GANTT_ORIGIN + 240" :height="data.height" role="img" aria-label="日期轴、今天和里程碑目标日期" class="gantt-axis">
    <text x="0" y="24" font-size="18">{{ data.from }} — {{ data.to }}</text>
    <g v-for="tick in ticks" :key="tick.date"><line :x1="tick.x" :x2="tick.x" y1="64" :y2="data.height" stroke="#e2e8f0" /><text :x="tick.x + 2" y="58" font-size="11" fill="#475569">{{ data.zoom === 'day' ? tick.date.slice(8) : tick.date.slice(5) }}</text><title>{{ tick.date }}</title></g>
    <g v-if="inRange(data.today)"><line :x1="x(data.today)" :x2="x(data.today)" y1="64" :y2="data.height" stroke="#dc2626" stroke-dasharray="4 3" /><text :x="x(data.today)" y="40" fill="#dc2626">今天 {{ data.today }}</text></g>
    <g v-for="milestone in milestones" :key="milestone.id"><line :x1="x(milestone.date) + data.scale" :x2="x(milestone.date) + data.scale" y1="64" :y2="data.height" stroke="#7c3aed" stroke-dasharray="2 5" /><text :x="x(milestone.date) + data.scale" y="78" fill="#7c3aed">◆</text><title>{{ milestone.name }} · {{ milestone.date }}</title></g>
    <text v-if="data.undatedY !== null" x="0" :y="data.undatedY" font-size="18" fill="#475569">未排期（位置不代表日期）</text>
  </svg>
</template>
<style scoped>.gantt-axis { pointer-events: none; overflow: visible; }</style>
