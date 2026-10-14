<script setup lang="ts">
/**
 * F5 workspace: a milestone x status board and a dependency graph over the
 * same filtered task data, plus a detail drawer.
 *
 * The page only reads and filters; every write is a controlled action that
 * carries `expected_version` (see MissionDetailDrawer). Filters, the active
 * view and the selected mission live in the URL so a link reproduces a view.
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import type { QueryParams } from '../api/client'
import { listTeamMembers } from '../api/auth'
import { listMilestones } from '../api/milestones'
import { getWorkspaceGraph, getWorkspaceOverview } from '../api/workspace'
import type {
  MissionPriority,
  MissionStatus,
  MissionType,
  User,
  WorkspaceGraph,
  WorkspaceOverview,
} from '../api/types'
import { PRIORITY_OPTIONS, STATUS_OPTIONS, TYPE_OPTIONS } from '../missionMeta'
import DependencyGraph from '../components/DependencyGraph.vue'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
import WorkspaceMilestoneBoard from '../components/WorkspaceMilestoneBoard.vue'

const route = useRoute()
const router = useRouter()

const view = ref<'overview' | 'graph'>('overview')
const overview = ref<WorkspaceOverview | null>(null)
const graph = ref<WorkspaceGraph | null>(null)
const loading = ref(false)
const error = ref('')
const lastRefreshed = ref('')
const members = ref<User[]>([])
const milestoneOptions = ref<{ id: string; name: string }[]>([])

const selectedId = ref<string | null>(null)
const drawerOpen = ref(false)
const columnLimit = ref(20)
const expandMode = ref<'one' | 'all'>('one')
const direction = ref<'both' | 'upstream' | 'downstream'>('both')
const relatedOnly = ref(false)
const showParentEdges = ref(false)
const relationListMode = ref(false)

const graphRef = ref<InstanceType<typeof DependencyGraph> | null>(null)

const filters = reactive<{
  q: string
  milestone: string
  status: MissionStatus | ''
  type: MissionType | ''
  priority: MissionPriority | ''
  assignee: string
  reviewer: string
  blocked: '' | 'true' | 'false'
}>({
  q: '',
  milestone: '',
  status: '',
  type: '',
  priority: '',
  assignee: '',
  reviewer: '',
  blocked: '',
})

const onlyMine = computed(() => filters.assignee === 'me')
const onlyBlocked = computed(() => filters.blocked === 'true')
const onlyReview = computed(() => filters.reviewer === 'me' && filters.status === 'Submitted')

const summary = computed(() => overview.value?.summary ?? null)

const relationRows = computed(() => {
  if (!graph.value) return []
  const byId = new Map(graph.value.nodes.map((node) => [node.id, node]))
  return graph.value.edges.map((edge) => ({
    edge,
    prerequisite: byId.get(edge.prerequisite_id),
    dependent: byId.get(edge.mission_id),
  }))
})

function baseParams(): QueryParams {
  return {
    q: filters.q || undefined,
    milestone: filters.milestone || undefined,
    status: filters.status || undefined,
    type: filters.type || undefined,
    priority: filters.priority || undefined,
    assignee: filters.assignee || undefined,
    reviewer: filters.reviewer || undefined,
    blocked: filters.blocked || undefined,
  }
}

async function loadOverview() {
  const data = await getWorkspaceOverview({
    ...baseParams(),
    column_limit: columnLimit.value,
  })
  overview.value = data
  lastRefreshed.value = data.generated_at
}

async function loadGraph() {
  const data = await getWorkspaceGraph({
    ...baseParams(),
    scope: relatedOnly.value && selectedId.value ? 'mission' : 'team',
    focus: selectedId.value || undefined,
    expand: relatedOnly.value ? 'all' : expandMode.value,
    direction: direction.value,
    include_parent: showParentEdges.value ? 'true' : undefined,
    context: relatedOnly.value ? 'false' : 'true',
    depth: 5,
  })
  graph.value = data
  lastRefreshed.value = data.generated_at
}

async function reload(options: { fitGraph?: boolean } = {}) {
  loading.value = true
  error.value = ''
  try {
    if (view.value === 'overview') {
      await loadOverview()
    } else {
      await loadGraph()
      if (options.fitGraph || selectedId.value) {
        await nextTick()
        if (options.fitGraph) graphRef.value?.fit()
        else if (selectedId.value) graphRef.value?.locate(selectedId.value)
      }
    }
  } catch (err) {
    error.value = err instanceof ApiException ? err.message : '加载失败，请重试'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

// --- URL <-> state -------------------------------------------------------- //
function readParam(value: unknown): string {
  if (Array.isArray(value)) return value.length ? String(value[0]) : ''
  return value == null ? '' : String(value)
}

function applyQuery() {
  const query = route.query
  view.value = readParam(query.view) === 'graph' ? 'graph' : 'overview'
  filters.q = readParam(query.q)
  filters.milestone = readParam(query.milestone)
  filters.status = (readParam(query.status) as MissionStatus) || ''
  filters.type = (readParam(query.type) as MissionType) || ''
  filters.priority = (readParam(query.priority) as MissionPriority) || ''
  filters.assignee = readParam(query.assignee)
  filters.reviewer = readParam(query.reviewer)
  const blocked = readParam(query.blocked)
  filters.blocked = blocked === 'true' || blocked === 'false' ? blocked : ''
  selectedId.value = readParam(query.selected) || null
  const limit = Number(readParam(query.limit))
  columnLimit.value = Number.isFinite(limit) && limit > 0 ? limit : 20
  relatedOnly.value = readParam(query.related) === 'true'
  relationListMode.value = readParam(query.relations) === 'true'
  showParentEdges.value = readParam(query.parent) === 'true'
  expandMode.value = readParam(query.expand) === 'all' ? 'all' : 'one'
  const dir = readParam(query.direction)
  direction.value = dir === 'upstream' || dir === 'downstream' ? dir : 'both'
}

function queryFromState(): Record<string, string> {
  const out: Record<string, string> = {}
  const set = (key: string, value: string) => {
    if (value) out[key] = value
  }
  if (view.value === 'graph') out.view = 'graph'
  set('q', filters.q)
  set('milestone', filters.milestone)
  set('status', filters.status)
  set('type', filters.type)
  set('priority', filters.priority)
  set('assignee', filters.assignee)
  set('reviewer', filters.reviewer)
  set('blocked', filters.blocked)
  set('selected', selectedId.value ?? '')
  if (columnLimit.value !== 20) set('limit', String(columnLimit.value))
  if (relatedOnly.value) set('related', 'true')
  if (relationListMode.value) set('relations', 'true')
  if (showParentEdges.value) set('parent', 'true')
  if (view.value === 'graph') {
    if (expandMode.value === 'all') set('expand', 'all')
    if (direction.value !== 'both') set('direction', direction.value)
  }
  return out
}

function syncUrl() {
  const next = queryFromState()
  const current = route.query
  const same =
    Object.keys(next).length === Object.keys(current).length &&
    Object.entries(next).every(([key, value]) => readParam(current[key]) === value)
  if (!same) void router.replace({ query: next })
}

// --- interactions --------------------------------------------------------- //
function onFilterChange() {
  columnLimit.value = 20
  syncUrl()
  void reload({ fitGraph: view.value === 'graph' })
}

function switchView(next: 'overview' | 'graph') {
  if (view.value === next) return
  view.value = next
  syncUrl()
  void reload({ fitGraph: next === 'graph' })
}

function toggleMine() {
  filters.assignee = filters.assignee === 'me' ? '' : 'me'
  onFilterChange()
}

function toggleBlocked() {
  filters.blocked = filters.blocked === 'true' ? '' : 'true'
  onFilterChange()
}

function toggleReview() {
  if (onlyReview.value) {
    filters.reviewer = ''
    filters.status = ''
  } else {
    filters.reviewer = 'me'
    filters.status = 'Submitted'
  }
  onFilterChange()
}

function onSelect(id: string) {
  selectedId.value = id
  drawerOpen.value = true
  syncUrl()
}

function onFocus(id: string) {
  selectedId.value = id
  if (view.value !== 'graph') {
    view.value = 'graph'
    syncUrl()
    void reload({ fitGraph: true })
  } else {
    syncUrl()
    graphRef.value?.locate(id)
  }
}

function onGraphOptionChange() {
  syncUrl()
  void reload()
}

function onLoadMore() {
  columnLimit.value += 20
  syncUrl()
  void reload()
}

function onDrawerChanged() {
  void reload({ fitGraph: false })
}

function onDrawerClose() {
  drawerOpen.value = false
}

function refresh() {
  void reload({ fitGraph: view.value === 'graph' })
}

const formatTime = (value: string) => (value ? new Date(value).toLocaleTimeString() : '')

onMounted(async () => {
  applyQuery()
  const [team, milestones] = await Promise.allSettled([
    listTeamMembers(),
    listMilestones({ page_size: 100 }),
  ])
  if (team.status === 'fulfilled') members.value = team.value
  if (milestones.status === 'fulfilled') {
    milestoneOptions.value = milestones.value.results.map((item) => ({
      id: item.id,
      name: item.name,
    }))
  }
  await reload({ fitGraph: view.value === 'graph' })
})
</script>

<template>
  <div class="workspace">
    <div class="page-header">
      <h2>工作台</h2>
      <div class="workspace__view-switch">
        <el-radio-group
          :model-value="view"
          size="default"
          @change="(value: string | number | boolean) => switchView(value as 'overview' | 'graph')"
        >
          <el-radio-button value="overview">概览</el-radio-button>
          <el-radio-button value="graph">依赖图</el-radio-button>
        </el-radio-group>
        <el-button @click="refresh">刷新</el-button>
        <el-button type="primary" @click="router.push({ name: 'mission-create' })">
          发布任务
        </el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-input
        v-model="filters.q"
        placeholder="搜索标题或内容"
        style="width: 200px"
        clearable
        @keyup.enter="onFilterChange"
        @clear="onFilterChange"
      />
      <el-select
        v-model="filters.milestone"
        placeholder="里程碑"
        clearable
        filterable
        style="width: 170px"
        @change="onFilterChange"
      >
        <el-option
          v-for="item in milestoneOptions"
          :key="item.id"
          :label="item.name"
          :value="item.id"
        />
        <el-option label="未归属里程碑" value="none" />
      </el-select>
      <el-select
        v-model="filters.status"
        placeholder="状态"
        clearable
        style="width: 130px"
        @change="onFilterChange"
      >
        <el-option
          v-for="item in STATUS_OPTIONS"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-select
        v-model="filters.assignee"
        placeholder="认领者"
        clearable
        filterable
        style="width: 150px"
        @change="onFilterChange"
      >
        <el-option label="我" value="me" />
        <el-option label="未认领" value="none" />
        <el-option
          v-for="member in members"
          :key="member.id"
          :label="member.display_name"
          :value="String(member.id)"
        />
      </el-select>
      <el-select
        v-model="filters.type"
        placeholder="类型"
        clearable
        style="width: 120px"
        @change="onFilterChange"
      >
        <el-option
          v-for="item in TYPE_OPTIONS"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-select
        v-model="filters.priority"
        placeholder="优先级"
        clearable
        style="width: 130px"
        @change="onFilterChange"
      >
        <el-option
          v-for="item in PRIORITY_OPTIONS"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-tooltip placement="top" content="按受阻状态筛选：存在未完成前置任务的任务即为受阻">
        <el-select
          v-model="filters.blocked"
          placeholder="受阻"
          clearable
          style="width: 120px"
          @change="onFilterChange"
        >
          <el-option label="仅受阻" value="true" />
          <el-option label="不受阻" value="false" />
        </el-select>
      </el-tooltip>
    </div>

    <div class="workspace__quick">
      <el-checkbox-button :model-value="onlyMine" @change="toggleMine">只看我的</el-checkbox-button>
      <el-checkbox-button :model-value="onlyBlocked" @change="toggleBlocked">只看阻塞</el-checkbox-button>
      <el-checkbox-button :model-value="onlyReview" @change="toggleReview">待我验收</el-checkbox-button>
    </div>

    <div v-if="summary" class="workspace__summary">
      <span class="workspace__summary-item">任务总数 {{ summary.matched_total }}</span>
      <span class="workspace__summary-item">
        有效完成 {{ summary.done }} / {{ summary.effective_total }}
      </span>
      <span class="workspace__summary-item workspace__summary-item--warn">
        受阻 {{ summary.blocked }}
      </span>
      <span class="workspace__summary-item">待验收 {{ summary.submitted }}</span>
      <span class="workspace__summary-item workspace__summary-item--danger">
        需复核 {{ summary.requires_revalidation }}
      </span>
    </div>

    <div v-if="view === 'graph'" class="workspace__graph-options">
      <span class="meta">展开选中任务的依赖</span>
      <el-radio-group
        v-model="expandMode"
        size="small"
        :disabled="!selectedId"
        @change="onGraphOptionChange"
      >
        <el-radio-button value="one">一跳</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
      <el-select
        v-model="direction"
        size="small"
        style="width: 130px"
        :disabled="!selectedId"
        @change="onGraphOptionChange"
      >
        <el-option label="上下游" value="both" />
        <el-option label="仅上游" value="upstream" />
        <el-option label="仅下游" value="downstream" />
      </el-select>
      <el-checkbox v-model="relatedOnly" :disabled="!selectedId" @change="onGraphOptionChange">
        只看相关
      </el-checkbox>
      <el-checkbox v-model="showParentEdges" @change="onGraphOptionChange">显示拆分关系</el-checkbox>
      <el-checkbox v-model="relationListMode" @change="syncUrl">关系列表</el-checkbox>
      <span class="meta">画布横轴是依赖层级，不是时间或状态</span>
    </div>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="workspace__error">
      {{ error }}
      <el-button link type="primary" @click="refresh">重试</el-button>
    </el-alert>

    <div v-loading="loading" class="workspace__main">
      <template v-if="view === 'overview'">
        <WorkspaceMilestoneBoard
          v-if="overview"
          :groups="overview.groups"
          :columns="overview.columns"
          :column-labels="overview.column_labels"
          :filters-active="overview.filters_active"
          :selected-id="selectedId"
          @select="onSelect"
          @focus="onFocus"
          @load-more="onLoadMore"
        />
      </template>
      <template v-else>
        <el-table
          v-if="relationListMode && graph"
          :data="relationRows"
          size="small"
          empty-text="没有依赖关系"
        >
          <el-table-column label="前置任务">
            <template #default="{ row }">{{ row.prerequisite?.title ?? '（不在当前范围）' }}</template>
          </el-table-column>
          <el-table-column label="依赖任务">
            <template #default="{ row }">{{ row.dependent?.title ?? '（不在当前范围）' }}</template>
          </el-table-column>
          <el-table-column label="是否满足" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.edge.is_satisfied ? 'success' : 'warning'">
                {{ row.edge.is_satisfied ? '已满足' : '等待' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="跨里程碑" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.edge.cross_milestone" size="small" type="info">跨里程碑</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onFocus(row.edge.mission_id)">
                定位依赖任务
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <template v-else-if="graph">
          <DependencyGraph
            ref="graphRef"
            :nodes="graph.nodes"
            :edges="graph.edges"
            :parent-edges="graph.parent_edges"
            :selected-id="selectedId"
            :show-parent-edges="showParentEdges"
            @select="onSelect"
            @focus="onFocus"
          />
          <div class="workspace__graph-meta">
            <span class="meta">
              节点 {{ graph.meta.node_count }}（匹配 {{ graph.meta.matched_included }}，上下文
              {{ graph.meta.context_count }}）· 依赖边 {{ graph.meta.edge_count }}
            </span>
            <el-tag v-if="graph.meta.nodes_truncated" type="warning" size="small">
              节点达到上限，请聚焦继续探索
            </el-tag>
            <el-tag v-if="graph.meta.edges_truncated" type="warning" size="small">
              依赖边达到上限，未展示全部
            </el-tag>
          </div>
        </template>
      </template>
    </div>

    <div class="workspace__legend">
      <span class="meta">状态：</span>
      <el-tag size="small" type="info">待认领</el-tag>
      <el-tag size="small" type="primary">进行中</el-tag>
      <el-tag size="small" type="warning">待验收</el-tag>
      <el-tag size="small" type="success">已完成</el-tag>
      <el-tag size="small" type="danger">已取消</el-tag>
      <span class="meta">
        · 依赖箭头方向：前置 → 依赖它的任务；实线灰=已满足，橙色=等待；虚线=父子拆分关系
      </span>
      <span class="meta">· 上次刷新 {{ formatTime(lastRefreshed) }}</span>
    </div>

    <MissionDetailDrawer
      :mission-id="selectedId"
      :open="drawerOpen"
      @close="onDrawerClose"
      @changed="onDrawerChanged"
      @focus="onFocus"
    />
  </div>
</template>

<style scoped>
.workspace {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}
.workspace__view-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}
.workspace__quick {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.workspace__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 14px;
}
.workspace__summary-item--warn {
  color: #b45309;
}
.workspace__summary-item--danger {
  color: #b91c1c;
}
.workspace__graph-options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.workspace__error {
  margin-bottom: 12px;
}
.workspace__main {
  min-height: 200px;
}
.workspace__graph-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
.workspace__legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
}
@media (max-width: 900px) {
  .workspace__view-switch {
    flex-wrap: wrap;
  }
}
</style>
