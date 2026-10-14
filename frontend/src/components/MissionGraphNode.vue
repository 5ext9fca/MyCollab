<script setup lang="ts">
/**
 * Vue Flow custom node (`type: mission`).
 *
 * Reuses MissionCard for display and adds the top/bottom handles that only act
 * as connection anchors — the graph reads top to bottom, so a prerequisite
 * leaves from the bottom and a dependent enters from the top. The graph is
 * read-only, so connecting is disabled on the handles and on the canvas.
 */
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
  <div class="ws-graph-node">
    <Handle
      :id="DEPENDENCY_TARGET_HANDLE"
      type="target"
      :position="Position.Top"
      :connectable="false"
    />
    <WorkspaceMissionCard
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
    <Handle
      :id="DEPENDENCY_SOURCE_HANDLE"
      type="source"
      :position="Position.Bottom"
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
</style>
