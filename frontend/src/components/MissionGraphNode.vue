<script setup lang="ts">
/** 任务卡片保留原操作，时间条按日期宽度绘制，依赖连接结束端。 */
import { Handle, Position } from '@vue-flow/core'

import type { MissionNodeData } from '../workspace/dto'
import { DEPENDENCY_SOURCE_HANDLE, DEPENDENCY_TARGET_HANDLE } from '../workspace/dto'
import WorkspaceMissionCard from './WorkspaceMissionCard.vue'

defineOptions({ inheritAttrs: false })

defineProps<{ data: MissionNodeData }>()

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
  (event: 'toggleChildren', id: string): void
}>()
</script>

<template>
  <div class="ws-graph-node" :class="{ 'ws-graph-node--gantt': !!data.gantt }" :style="data.gantt ? { width: data.gantt.width + 'px' } : undefined">
    <Handle
      :id="DEPENDENCY_TARGET_HANDLE"
      type="target"
      :position="data.gantt ? Position.Right : Position.Top"
      :connectable="false"
    />
    <WorkspaceMissionCard
      :class="{ 'gantt-caption': !!data.gantt }"
      :node="data.node"
      :selected="data.selected"
      :dimmed="data.dimmed"
      :milestone-color="data.color"
      :depth="data.depth"
      :descendant-count="data.descendantCount"
      :collapsed="data.collapsed"
      compact
      @select="emit('select', $event)"
      @focus="emit('focus', $event)"
      @toggle-children="emit('toggleChildren', $event)"
    />
    <button v-if="data.gantt" class="gantt-bar" :class="{ 'gantt-bar--incomplete': data.gantt.incomplete, 'gantt-bar--dim': data.dimmed, 'gantt-bar--selected': data.selected }" :style="{ background: data.gantt.unscheduled ? '#e2e8f0' : data.color }" :title="data.node.title + '：' + data.gantt.label" :aria-label="data.node.title + '：' + data.gantt.label" @click.stop="emit('select', data.node.id)">
      {{ data.gantt.unscheduled ? '未排期' : data.gantt.clippedStart ? '←' : data.gantt.clippedEnd ? '→' : ' ' }}
    </button>
    <span v-if="data.gantt" class="gantt-dates">{{ data.gantt.label }}</span>
    <Handle
      :id="DEPENDENCY_SOURCE_HANDLE"
      type="source"
      :position="data.gantt ? Position.Right : Position.Bottom"
      :connectable="false"
    />
  </div>
</template>

<style scoped>
.ws-graph-node {
  width: 220px;
}
.ws-graph-node :deep(.vue-flow__handle) {
  width: 8px;
  height: 8px;
  background: #94a3b8;
  border: 1px solid #fff;
}
.ws-graph-node--gantt { height: 24px; }
.gantt-caption { position: absolute; top: -122px; left: 0; width: 220px; }
.gantt-bar { width: 100%; height: 24px; border: 1px solid #334155; border-radius: 4px; cursor: pointer; color: #0f172a; }
.gantt-bar--incomplete { border-style: dashed; }
.gantt-bar--dim { opacity: .25; }
.gantt-bar--selected { outline: 3px solid #2563eb; }
.gantt-dates { position: absolute; top: 28px; left: 0; white-space: nowrap; font-size: 11px; color: #475569; }
</style>
