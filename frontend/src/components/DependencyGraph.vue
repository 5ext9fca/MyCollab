<script setup lang="ts">
/** 现有依赖画布升级为甘特图，保留只读交互、焦点与父子折叠。 */
import { computed, nextTick } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { Edge, Node } from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import { computeGanttLayout } from '../composables/useGanttLayout'
import GanttAxis from './GanttAxis.vue'
import { buildDependencyEdges, buildMissionNodes, NODE_HEIGHT, NODE_WIDTH } from '../workspace/dto'
import type { GroupInfo } from '../workspace/dto'
import { directRelations } from '../workspace/dependencyTraversal'
import MissionGraphNode from './MissionGraphNode.vue'

const props = withDefaults(
  defineProps<{
    dateFrom?: string
    dateTo?: string
    today?: string
    zoom?: 'day' | 'week'
    nodes: WorkspaceNode[]
    edges: WorkspaceEdge[]
    selectedId?: string | null
    /** Parent/child grouping; null leaves every node independent. */
    grouping?: GroupInfo | null
    /** Extra ids to emphasise (e.g. "all upstream"): null keeps direct-only. */
    emphasisIds?: Set<string> | null
  }>(),
  { selectedId: null, grouping: null, emphasisIds: null, zoom: 'day' },
)

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
  (event: 'edgeSelect', edge: WorkspaceEdge): void
  (event: 'toggleCollapse', id: string): void
}>()

const today = computed(() => props.today ?? new Date().toISOString().slice(0, 10))
const from = computed(() => props.dateFrom ?? today.value)
const to = computed(() => props.dateTo ?? new Date(Date.parse(`${from.value}T00:00:00Z`) + 28 * 86400000).toISOString().slice(0, 10))
const layout = computed(() => computeGanttLayout(props.nodes, props.edges, props.grouping, from.value, to.value, props.zoom))
const { fitView, setCenter, findNode, onNodesInitialized, onNodeClick, onEdgeClick } = useVueFlow()

let fitted = false

const emphasis = computed(() => {
  if (props.emphasisIds) return props.emphasisIds
  if (!props.selectedId) return null
  const { prerequisites, dependents } = directRelations(props.selectedId, props.edges)
  return new Set<string>([props.selectedId, ...prerequisites, ...dependents])
})

/**
 * The cards actually on the canvas, after collapsed subtrees were merged. An
 * edge is coloured by its *visible* source endpoint; an edge whose source is not
 * here (an abnormal relation the backend flagged) stays neutral.
 */
const visibleNodeIds = computed(() => new Set(props.nodes.map((node) => node.id)))

const flowNodes = computed<Node[]>(() => [
  { id: '__gantt_axis__', type: 'gantt-axis', position: { x: 0, y: 0 }, selectable: false, draggable: false, connectable: false, deletable: false, zIndex: -1,
    style: { pointerEvents: 'none' }, data: { from: from.value, to: to.value, today: today.value, scale: layout.value.scale,
      width: layout.value.width, height: layout.value.height, zoom: props.zoom, nodes: props.nodes, undatedY: layout.value.undatedY } },
  ...buildMissionNodes(layout.value.rows, layout.value.positions, emphasis.value, props.selectedId, props.grouping).map(node => ({ ...node,
    style: { width: `${layout.value.bars.get(node.id)!.width}px` }, data: { ...node.data!, gantt: layout.value.bars.get(node.id)! } })),
])

const flowEdges = computed<Edge[]>(() =>
  buildDependencyEdges(props.edges, props.selectedId, visibleNodeIds.value),
)

onNodesInitialized(() => {
  if (fitted || !props.nodes.length) return
  fitted = true
  void nextTick(() => fitView({ padding: 0.15 }))
})

onNodeClick(({ node }) => { if (node.type === 'mission') emit('select', node.id) })
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
  void setCenter(node.position.x + (layout.value.bars.get(id)?.width ?? NODE_WIDTH) / 2, node.position.y - NODE_HEIGHT / 2, {
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
        <template #node-gantt-axis="axisProps"><GanttAxis :data="axisProps.data" /></template>
        <template #node-mission="nodeProps">
          <MissionGraphNode
            v-bind="nodeProps"
            @select="emit('select', $event)"
            @focus="emit('focus', $event)"
            @toggle-children="emit('toggleCollapse', $event)"
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
.graph :deep(.ws-edge) .vue-flow__edge-path,
.graph :deep(.ws-edge) path {
  stroke-width: 2;
}
/* Satisfied vs pending is a line-style cue, never a stroke colour: the stroke
 * colour belongs to the source mission. */
.graph :deep(.ws-edge--pending) .vue-flow__edge-path,
.graph :deep(.ws-edge--pending) path {
  stroke-dasharray: 6 4;
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
