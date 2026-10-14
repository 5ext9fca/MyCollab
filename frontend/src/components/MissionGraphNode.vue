<script setup lang="ts">
/**
 * Vue Flow custom node (`type: mission`).
 *
 * Reuses MissionCard for display and adds the left/right handles that only act
 * as connection anchors — the graph is read-only, so connecting is disabled on
 * the handles and on the canvas.
 */
import { Handle, Position } from '@vue-flow/core'

import type { MissionNodeData } from '../workspace/dto'
import WorkspaceMissionCard from './WorkspaceMissionCard.vue'

defineOptions({ inheritAttrs: false })

defineProps<{ data: MissionNodeData }>()

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
}>()
</script>

<template>
  <div class="ws-graph-node">
    <Handle type="target" :position="Position.Left" :connectable="false" />
    <WorkspaceMissionCard
      :node="data.node"
      :selected="data.selected"
      :dimmed="data.dimmed"
      :milestone-color="data.color"
      compact
      @select="emit('select', $event)"
      @focus="emit('focus', $event)"
    />
    <Handle type="source" :position="Position.Right" :connectable="false" />
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
