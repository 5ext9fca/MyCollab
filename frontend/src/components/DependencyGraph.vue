<script setup lang="ts">
/**
 * F5 dependency graph.
 *
 * Renders a layered DAG (prerequisite -> dependent) with an accessible
 * pan/zoom/fit canvas. It only shows and navigates; every business rule and
 * permission is still enforced by the backend.
 */
import { computed, onMounted, ref, watch } from 'vue'

import type { WorkspaceEdge, WorkspaceNode, WorkspaceParentEdge } from '../api/types'
import { NODE_HEIGHT, NODE_WIDTH, directRelations, layoutGraph } from '../workspaceLayout'
import WorkspaceMissionCard from './WorkspaceMissionCard.vue'

const props = withDefaults(
  defineProps<{
    nodes: WorkspaceNode[]
    edges: WorkspaceEdge[]
    parentEdges?: WorkspaceParentEdge[]
    selectedId?: string | null
    showParentEdges?: boolean
  }>(),
  { parentEdges: () => [], selectedId: null, showParentEdges: false },
)

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
}>()

const viewport = ref<HTMLElement | null>(null)
const scale = ref(1)
const tx = ref(40)
const ty = ref(40)

const layout = computed(() =>
  layoutGraph(props.nodes, props.edges, props.showParentEdges ? props.parentEdges : []),
)

const emphasis = computed(() => {
  if (!props.selectedId) return null
  const { prerequisites, dependents } = directRelations(props.selectedId, props.edges)
  const set = new Set<string>([props.selectedId, ...prerequisites, ...dependents])
  return set
})

function isDimmed(id: string): boolean {
  if (!emphasis.value) return false
  return !emphasis.value.has(id)
}

function edgeClass(edge: WorkspaceEdge): Record<string, boolean> {
  const touchesSelected =
    !!props.selectedId &&
    (edge.mission_id === props.selectedId || edge.prerequisite_id === props.selectedId)
  return {
    'graph-edge--satisfied': edge.is_satisfied,
    'graph-edge--pending': !edge.is_satisfied,
    'graph-edge--highlight': touchesSelected,
    'graph-edge--dim': !!props.selectedId && !touchesSelected,
  }
}

function clampScale(value: number): number {
  return Math.min(2.5, Math.max(0.3, value))
}

function fit() {
  const element = viewport.value
  if (!element) return
  const vw = element.clientWidth || 800
  const vh = element.clientHeight || 520
  const width = layout.value.width || 1
  const height = layout.value.height || 1
  const next = clampScale(Math.min((vw - 60) / width, (vh - 60) / height, 1))
  scale.value = next
  tx.value = (vw - width * next) / 2
  ty.value = (vh - height * next) / 2
}

function reset() {
  scale.value = 1
  tx.value = 40
  ty.value = 40
}

function zoom(factor: number) {
  const element = viewport.value
  const vw = element?.clientWidth ?? 800
  const vh = element?.clientHeight ?? 520
  const cx = vw / 2
  const cy = vh / 2
  const next = clampScale(scale.value * factor)
  tx.value = cx - (cx - tx.value) * (next / scale.value)
  ty.value = cy - (cy - ty.value) * (next / scale.value)
  scale.value = next
}

function locate(id: string) {
  const element = viewport.value
  const target = layout.value.positions.get(id)
  if (!element || !target) return
  const vw = element.clientWidth || 800
  const vh = element.clientHeight || 520
  scale.value = Math.max(scale.value, 0.8)
  tx.value = vw / 2 - (target.x + NODE_WIDTH / 2) * scale.value
  ty.value = vh / 2 - (target.y + NODE_HEIGHT / 2) * scale.value
}

let panning = false
let startX = 0
let startY = 0
let startTx = 0
let startTy = 0

function onPointerDown(event: PointerEvent) {
  const target = event.target as HTMLElement
  if (target.closest('.ws-card') || target.closest('.graph__toolbar')) return
  panning = true
  startX = event.clientX
  startY = event.clientY
  startTx = tx.value
  startTy = ty.value
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!panning) return
  tx.value = startTx + (event.clientX - startX)
  ty.value = startTy + (event.clientY - startY)
}

function onPointerUp(event: PointerEvent) {
  panning = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId)
}

function onWheel(event: WheelEvent) {
  const element = viewport.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const cx = event.clientX - rect.left
  const cy = event.clientY - rect.top
  const next = clampScale(scale.value * (event.deltaY < 0 ? 1.1 : 1 / 1.1))
  tx.value = cx - (cx - tx.value) * (next / scale.value)
  ty.value = cy - (cy - ty.value) * (next / scale.value)
  scale.value = next
}

watch(
  () => props.selectedId,
  (id) => {
    if (id) locate(id)
  },
)

onMounted(fit)

defineExpose({ fit, reset, locate, zoom })
</script>

<template>
  <div class="graph">
    <div class="graph__toolbar">
      <el-button size="small" @click="zoom(1 / 1.2)">缩小</el-button>
      <el-button size="small" @click="zoom(1.2)">放大</el-button>
      <el-button size="small" @click="fit">适应全部</el-button>
      <el-button size="small" @click="reset">重置布局</el-button>
      <el-button
        size="small"
        :disabled="!selectedId"
        @click="selectedId && locate(selectedId)"
      >
        定位选中
      </el-button>
    </div>

    <div
      ref="viewport"
      class="graph__viewport"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @wheel.prevent="onWheel"
    >
      <div
        class="graph__canvas"
        :style="{
          width: `${layout.width}px`,
          height: `${layout.height}px`,
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
        }"
      >
        <svg class="graph__svg" :width="layout.width || 1" :height="layout.height || 1">
          <defs>
            <marker
              id="ws-arrow-satisfied"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              marker-width="7"
              marker-height="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
            </marker>
            <marker
              id="ws-arrow-pending"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              marker-width="7"
              marker-height="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b" />
            </marker>
          </defs>

          <path
            v-for="item in layout.parentEdges"
            :key="`parent-${item.edge.parent_id}-${item.edge.child_id}`"
            class="graph-edge graph-edge--parent"
            :d="item.path"
          />
          <path
            v-for="item in layout.dependencyEdges"
            :key="item.edge.id"
            class="graph-edge"
            :class="edgeClass(item.edge)"
            :d="item.path"
            :marker-end="
              item.edge.is_satisfied
                ? 'url(#ws-arrow-satisfied)'
                : 'url(#ws-arrow-pending)'
            "
          />
        </svg>

        <div
          v-for="item in layout.nodes"
          :key="item.node.id"
          class="graph__node"
          :style="{ left: `${item.x}px`, top: `${item.y}px` }"
        >
          <WorkspaceMissionCard
            :node="item.node"
            :selected="item.node.id === selectedId"
            :dimmed="isDimmed(item.node.id)"
            @select="emit('select', $event)"
            @focus="emit('focus', $event)"
          />
        </div>
      </div>

      <el-empty v-if="!nodes.length" description="没有可展示的任务" />
    </div>
  </div>
</template>

<style scoped>
.graph {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}
.graph__toolbar {
  display: flex;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 8px 8px 0 0;
}
.graph__viewport {
  position: relative;
  height: 560px;
  overflow: hidden;
  touch-action: none;
  cursor: grab;
}
.graph__canvas {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}
.graph__svg {
  position: absolute;
  top: 0;
  left: 0;
  overflow: visible;
}
.graph__node {
  position: absolute;
  width: 220px;
}
.graph-edge {
  fill: none;
  stroke-width: 2;
}
.graph-edge--satisfied {
  stroke: #94a3b8;
}
.graph-edge--pending {
  stroke: #f59e0b;
}
.graph-edge--parent {
  stroke: #cbd5e1;
  stroke-dasharray: 6 4;
  stroke-width: 1.5;
}
.graph-edge--highlight {
  stroke-width: 3;
}
.graph-edge--dim {
  opacity: 0.25;
}
</style>
