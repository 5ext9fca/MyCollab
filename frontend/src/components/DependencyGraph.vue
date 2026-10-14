<script setup lang="ts">
/**
 * F5 dependency graph, rendered with Vue Flow.
 *
 * Read-only by construction: node dragging, connecting, edge re-linking and the
 * delete shortcut are all disabled, and no Vue Flow event ever writes to the
 * business API. Positions come from Dagre (`useDagreLayout`); a pure status
 * refresh keeps the same coordinates. Only direct relations are emphasised by
 * default — "all upstream/downstream" is an explicit action in the page.
 */
import { computed, nextTick, watch } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { Edge, Node } from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import type { WorkspaceEdge, WorkspaceNode, WorkspaceParentEdge } from '../api/types'
import { useDagreLayout } from '../composables/useDagreLayout'
import {
  buildDependencyEdges,
  buildMissionNodes,
  buildParentEdges,
  NODE_HEIGHT,
  NODE_WIDTH,
} from '../workspace/dto'
import type { MissionNodeData } from '../workspace/dto'
import { directRelations } from '../workspace/dependencyTraversal'
import MissionGraphNode from './MissionGraphNode.vue'

const props = withDefaults(
  defineProps<{
    nodes: WorkspaceNode[]
    edges: WorkspaceEdge[]
    parentEdges?: WorkspaceParentEdge[]
    selectedId?: string | null
    showParentEdges?: boolean
    /** Extra ids to emphasise (e.g. "all upstream"): null keeps direct-only. */
    emphasisIds?: Set<string> | null
  }>(),
  { parentEdges: () => [], selectedId: null, showParentEdges: false, emphasisIds: null },
)

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
  (event: 'edgeSelect', edge: WorkspaceEdge): void
}>()

const { positions, update } = useDagreLayout()
const { fitView, setCenter, findNode, onNodesInitialized, onNodeClick, onEdgeClick } = useVueFlow()

let fitted = false

const emphasis = computed(() => {
  if (props.emphasisIds) return props.emphasisIds
  if (!props.selectedId) return null
  const { prerequisites, dependents } = directRelations(props.selectedId, props.edges)
  return new Set<string>([props.selectedId, ...prerequisites, ...dependents])
})

const flowNodes = computed<Node<MissionNodeData>[]>(() =>
  buildMissionNodes(props.nodes, positions.value, emphasis.value, props.selectedId),
)

const flowEdges = computed<Edge[]>(() => {
  const dependencyEdges = buildDependencyEdges(props.edges, props.selectedId)
  const parentEdges = props.showParentEdges ? buildParentEdges(props.parentEdges) : []
  return [...parentEdges, ...dependencyEdges]
})

/** Recompute Dagre coordinates only when the structure changed. */
function applyLayout() {
  update(props.nodes, props.edges)
}

applyLayout()
watch(() => [props.nodes, props.edges], applyLayout)

onNodesInitialized(() => {
  if (fitted || !props.nodes.length) return
  fitted = true
  void nextTick(() => fitView({ padding: 0.15 }))
})

onNodeClick(({ node }) => emit('select', node.id))
onEdgeClick(({ edge }) => {
  const data = edge.data as { edge?: WorkspaceEdge } | undefined
  if (data?.edge) emit('edgeSelect', data.edge)
})

function fit() {
  fitted = true
  void fitView({ padding: 0.15 })
}

function reset() {
  void fitView({ padding: 0.15 })
}

function locate(id: string) {
  const node = findNode(id)
  if (!node) return
  void setCenter(node.position.x + NODE_WIDTH / 2, node.position.y + NODE_HEIGHT / 2, {
    zoom: 1,
    duration: 300,
  })
}

defineExpose({ fit, reset, locate })
</script>

<template>
  <div class="graph">
    <div class="graph__host">
      <VueFlow
        :nodes="flowNodes"
        :edges="flowEdges"
        :min-zoom="0.2"
        :max-zoom="2.5"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :edges-updatable="false"
        :delete-key-code="null"
        :zoom-on-double-click="false"
        :elevate-edges-on-select="true"
        :default-viewport="{ x: 0, y: 0, zoom: 0.9 }"
      >
        <template #node-mission="nodeProps">
          <MissionGraphNode
            v-bind="nodeProps"
            @select="emit('select', $event)"
            @focus="emit('focus', $event)"
          />
        </template>
        <Controls :show-interactive="false" position="top-right" />
      </VueFlow>
      <el-empty v-if="!nodes.length" class="graph__empty" description="没有可展示的任务" />
    </div>
  </div>
</template>

<style scoped>
.graph {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
  overflow: hidden;
}
.graph__host {
  position: relative;
  height: 560px;
  width: 100%;
}
.graph__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
}
.graph :deep(.ws-edge--satisfied) .vue-flow__edge-path,
.graph :deep(.ws-edge--satisfied) path {
  stroke: #94a3b8;
  stroke-width: 2;
}
.graph :deep(.ws-edge--pending) .vue-flow__edge-path,
.graph :deep(.ws-edge--pending) path {
  stroke: #f59e0b;
  stroke-width: 2;
}
.graph :deep(.ws-edge--parent) .vue-flow__edge-path,
.graph :deep(.ws-edge--parent) path {
  stroke: #cbd5e1;
  stroke-dasharray: 6 4;
  stroke-width: 1.5;
}
.graph :deep(.ws-edge--highlight) .vue-flow__edge-path,
.graph :deep(.ws-edge--highlight) path {
  stroke-width: 3;
}
.graph :deep(.ws-edge--dim) {
  opacity: 0.25;
}
.graph :deep(.vue-flow__edge-text) {
  font-size: 11px;
  fill: #b45309;
}
</style>
