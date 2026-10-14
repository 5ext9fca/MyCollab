<script setup lang="ts">
/** F5 mission card shared by the board and the graph node. */
import { computed } from 'vue'

import type { WorkspaceNode } from '../api/types'
import { PRIORITY_TAG, TYPE_LABELS, TYPE_TAG } from '../missionMeta'
import StatusTag from './StatusTag.vue'

const props = withDefaults(
  defineProps<{
    node: WorkspaceNode
    selected?: boolean
    dimmed?: boolean
    /** Graph nodes rendered at a reduced size show only the core fields. */
    compact?: boolean
    /** Milestone swatch; empty keeps the neutral board card look. */
    milestoneColor?: string
    /** Nesting depth inside a parent/child family (0 = root/ungrouped). */
    depth?: number
    /** Visible descendants (whole subtree) used by the collapse control. */
    descendantCount?: number
    /** True when this node's subtree is collapsed in the graph. */
    collapsed?: boolean
  }>(),
  {
    selected: false,
    dimmed: false,
    compact: false,
    milestoneColor: '',
    depth: 0,
    descendantCount: 0,
    collapsed: false,
  },
)

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'focus', id: string): void
  (event: 'toggleChildren', id: string): void
}>()

const shortId = (id: string) => id.slice(0, 8)

/** Tooltip for the milestone swatch, so colour is never the only cue. */
const milestoneTitle = computed(() => `所属里程碑：${props.node.milestone_name ?? '未归属里程碑'}`)

/** Subtask depth is conveyed by indentation; keep it in the label too. */
const cardLabel = computed(
  () => `${props.depth > 0 ? '子任务，' : ''}任务 ${props.node.title}`,
)

/** Unfinished prerequisites and unfinished children never collapse into one. */
const unfinishedPrerequisites = computed(() => props.node.blocking_count)
const unfinishedChildren = computed(() => props.node.unfinished_child_count)
const noUnfinishedRelations = computed(
  () => unfinishedPrerequisites.value === 0 && unfinishedChildren.value === 0,
)

function onSelect() {
  emit('select', props.node.id)
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    onSelect()
  }
}
</script>

<template>
  <div
    class="ws-card"
    :class="{
      'ws-card--selected': selected,
      'ws-card--dimmed': dimmed,
      'ws-card--context': node.is_context,
      'ws-card--cancelled': node.status === 'Cancelled',
      'ws-card--compact': compact,
      'ws-card--milestoned': !!milestoneColor,
    }"
    :style="milestoneColor ? { '--ws-milestone': milestoneColor } : undefined"
    role="button"
    tabindex="0"
    :aria-pressed="selected"
    :aria-label="cardLabel"
    :title="node.title"
    @click.stop="onSelect"
    @keydown="onKey"
  >
    <div class="ws-card__head">
      <span class="ws-card__head-left">
        <span
          v-if="milestoneColor"
          class="ws-card__swatch"
          :title="milestoneTitle"
          :aria-label="milestoneTitle"
        />
        <span class="ws-card__id">#{{ shortId(node.id) }}</span>
      </span>
      <StatusTag :status="node.status" />
    </div>

    <div class="ws-card__title">{{ node.title }}</div>

    <div class="ws-card__badges">
      <el-tag :type="TYPE_TAG[node.type]" size="small" disable-transitions>
        {{ TYPE_LABELS[node.type] }}
      </el-tag>
      <el-tag :type="PRIORITY_TAG[node.priority]" size="small" disable-transitions>
        {{ node.priority }}
      </el-tag>
      <el-tag v-if="node.is_blocked" type="warning" size="small" disable-transitions>
        受阻
      </el-tag>
      <el-tag v-if="node.requires_revalidation" type="danger" size="small" disable-transitions>
        需复核
      </el-tag>
      <el-tag v-if="node.is_context" type="info" size="small" disable-transitions>
        上下文
      </el-tag>
    </div>

    <div v-if="compact && descendantCount" class="ws-card__children">
      <button
        type="button"
        class="ws-card__toggle"
        :aria-expanded="!collapsed"
        :aria-label="collapsed ? '展开子任务' : '折叠子任务'"
        @click.stop="emit('toggleChildren', node.id)"
      >
        <span class="ws-card__toggle-icon" aria-hidden="true">{{ collapsed ? '▸' : '▾' }}</span>
        子任务 {{ descendantCount }}<template v-if="collapsed">（依赖已合并）</template>
      </button>
    </div>

    <div v-if="!compact" class="ws-card__meta">
      <span v-if="node.assignee">认领者：{{ node.assignee.display_name }}</span>
      <span v-else class="ws-card__unassigned">未认领</span>
      <span v-if="node.milestone_name"> · {{ node.milestone_name }}</span>
      <span v-if="node.parent_id"> · 父 #{{ shortId(node.parent_id) }}</span>
    </div>

    <div v-if="!compact" class="ws-card__relations">
      <span v-if="unfinishedPrerequisites" class="ws-card__relation">
        前置未完成 {{ unfinishedPrerequisites }}
      </span>
      <span v-if="unfinishedChildren" class="ws-card__relation">
        子任务未完成 {{ unfinishedChildren }}
      </span>
      <span v-if="noUnfinishedRelations" class="ws-card__relation">无未完成前置或子任务</span>
    </div>

    <div v-if="!compact" class="ws-card__foot">
      <el-button link type="primary" size="small" @click.stop="emit('focus', node.id)">
        查看依赖
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.ws-card {
  width: 220px;
  min-height: 92px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgb(15 23 42 / 6%);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
}
.ws-card:focus-visible {
  outline: 2px solid #409eff;
  outline-offset: 1px;
}
.ws-card--selected {
  border-color: #1d4ed8;
  box-shadow: 0 0 0 2px rgb(29 78 216 / 35%);
}
.ws-card--dimmed {
  opacity: 0.45;
}
.ws-card--context {
  border-style: dashed;
}
.ws-card--cancelled .ws-card__title {
  text-decoration: line-through;
  color: #6b7280;
}
.ws-card--compact {
  /* Fixed height: the parent/child stack places cards by NODE_HEIGHT. */
  height: 120px;
  overflow: hidden;
}
.ws-card--compact .ws-card__title {
  -webkit-line-clamp: 1;
}
.ws-card--compact .ws-card__badges {
  flex-wrap: nowrap;
  overflow: hidden;
}
.ws-card__children {
  display: flex;
}
.ws-card__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  height: 20px;
  padding: 0 6px;
  font-size: 12px;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  cursor: pointer;
}
.ws-card__toggle:hover {
  background: #e2e8f0;
}
.ws-card__toggle-icon {
  font-size: 10px;
  line-height: 1;
}
.ws-card--milestoned {
  border-left: 4px solid var(--ws-milestone);
  background: color-mix(in srgb, var(--ws-milestone) 7%, #fff);
}
.ws-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.ws-card__head-left {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.ws-card__swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: var(--ws-milestone);
  flex: none;
}
.ws-card__id {
  color: #94a3b8;
  font-size: 11px;
}
.ws-card__title {
  font-weight: 600;
  font-size: 14px;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.ws-card__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.ws-card__meta {
  color: #6b7280;
  font-size: 12px;
}
.ws-card__unassigned {
  color: #b45309;
}
.ws-card__relations {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ws-card__foot {
  display: flex;
  justify-content: flex-end;
  margin-top: auto;
}
.ws-card__relation {
  color: #6b7280;
  font-size: 12px;
}
</style>
