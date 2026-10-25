<script setup lang="ts">
/**
 * F5 workspace page (WorkspacePage).
 *
 * Owns the view switch, the URL state and the request sequence; it renders the
 * milestone board or the Vue Flow dependency graph, plus the shared detail
 * drawer. It only reads and filters — every write is a controlled action that
 * carries `expected_version` (see MissionDetailDrawer).
 *
 * A monotonic request sequence makes the newest filter win: a slow response can
 * never overwrite a newer one, and the graph layout is derived from the applied
 * response only.
 */
import { watch, computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiException } from '../api/client'
import type { QueryParams } from '../api/client'
import { listTeamMembers } from '../api/auth'
import { listMilestones } from '../api/milestones'
import { getWorkspaceGraph, getWorkspaceOverview } from '../api/workspace'
import type { User, WorkspaceEdge, WorkspaceGraph, WorkspaceOverview } from '../api/types'
import type { QuickKey, WorkspaceFilters } from '../workspace/filters'
import { emptyFilters, readParam } from '../workspace/filters'
import { collectRelated, relatedHighlight } from '../workspace/dependencyTraversal'
import { edgeStrokeColor } from '../workspace/dto'
import { milestoneColor, milestoneLabel } from '../workspace/milestoneColor'
import { groupByParent, revealPath } from '../workspace/parentGrouping'
import { dependencyLevels } from '../composables/useGraphLayout'
import DependencyGraph from '../components/DependencyGraph.vue'
import MilestoneBoard from '../components/MilestoneBoard.vue'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
import MissionSchedule from '../components/MissionSchedule.vue'
import StatusTag from '../components/StatusTag.vue'
import SavedViewsBar from '../components/SavedViewsBar.vue'
import MissionQueryForm from '../components/MissionQueryForm.vue'
import { notifyChanged } from '../api/notifications'
import WorkspaceFilterBar from '../components/WorkspaceFilterBar.vue'

const route = useRoute()
const router = useRouter()

const view = ref<'overview' | 'graph'>('overview')
const overview = ref<WorkspaceOverview | null>(null)
const graph = ref<WorkspaceGraph | null>(null)
const dateFrom = ref('')
const dateTo = ref('')
const dateZoom = ref<'day' | 'week'>('day')
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
const showParentRelations = ref(true)
const collapsedParents = ref<Set<string>>(new Set())
const relationListMode = ref(false)
const selectedEdge = ref<WorkspaceEdge | null>(null)

const filters = ref<WorkspaceFilters>(emptyFilters())
const extraFilters = ref<QueryParams>({})
const savedViewId = ref('')
const graphRef = ref<InstanceType<typeof DependencyGraph> | null>(null)

const onlyMine = computed(() => filters.value.assignee === 'me')
const onlyBlocked = computed(() => filters.value.blocked === 'true')
const onlyReview = computed(
  () => filters.value.reviewer === 'me' && filters.value.status === 'Submitted',
)
const onlyRevalidation = computed(() => filters.value.revalidation === 'true')

const summary = computed(() => view.value === 'overview' ? overview.value?.summary ?? null : null)
const graphMeta = computed(() => graph.value?.meta ?? null)
const graphNodes = computed(() => graph.value?.nodes ?? [])
const graphEdges = computed(() => graph.value?.edges ?? [])

/**
 * Parent/child grouping. When enabled, children are mounted under their parent
 * and every collapsed subtree is folded onto its parent. The page owns this
 * state so the canvas, the milestone legend and the relation list all describe
 * exactly the same visible view.
 */
const grouped = computed(() => {
  if (!showParentRelations.value || !graph.value) return null
  return groupByParent(
    graphNodes.value,
    graphEdges.value,
    graph.value.parent_edges,
    collapsedParents.value,
  )
})
const visibleNodes = computed(() => grouped.value?.nodes ?? graphNodes.value)
const visibleEdges = computed(() => grouped.value?.edges ?? graphEdges.value)

/**
 * A collapsed merge can re-point two children onto their parents and produce a
 * cycle the layering has to break. The layout stays usable, but the page must
 * say so instead of implying the edge direction is complete.
 */
const graphHasCycle = computed(() => {
  if (view.value !== 'graph' || !graph.value) return false
  return dependencyLevels(
    visibleNodes.value.map((node) => node.id),
    visibleEdges.value,
  ).hasCycle
})

/**
 * Highlight beyond the default direct relations: "only related" keeps the
 * whole loaded neighbourhood, and an explicit "all upstream/downstream" keeps
 * the walk in that direction. Null means "direct relations only".
 */
const emphasisIds = computed<Set<string> | null>(() => {
  if (!selectedId.value) return null
  if (relatedOnly.value) return relatedHighlight(selectedId.value, visibleEdges.value, 'both')
  if (expandMode.value === 'all' && direction.value !== 'both') {
    return relatedHighlight(selectedId.value, visibleEdges.value, direction.value)
  }
  return null
})

const truncationLabels: Record<string, string> = {
  node_limit: '节点达到上限',
  context_limit: '上下文节点达到上限',
  edge_limit: '依赖边达到上限',
}

const relationRows = computed(() => {
  const byId = new Map(visibleNodes.value.map((node) => [node.id, node]))
  return visibleEdges.value.map((edge) => ({
    edge,
    prerequisite: byId.get(edge.prerequisite_id),
    dependent: byId.get(edge.mission_id),
  }))
})

const selectedRelations = computed(() => {
  if (!selectedId.value || !graph.value) return null
  const upstream = collectRelated(selectedId.value, visibleEdges.value, 'upstream')
  const downstream = collectRelated(selectedId.value, visibleEdges.value, 'downstream')
  const byId = new Map(visibleNodes.value.map((node) => [node.id, node]))
  const titles = (ids: string[]) =>
    ids.map((id) => byId.get(id)?.title ?? id.slice(0, 8)).join('、') || '无'
  return { upstream: titles(upstream), downstream: titles(downstream) }
})

/**
 * The selected edge is coloured by its visible source mission, exactly like the
 * canvas. The banner names both endpoints so the source mission is readable in
 * words, not only by colour.
 */
const selectedEdgeInfo = computed(() => {
  const current = selectedEdge.value
  if (!current) return null
  const byId = new Map(visibleNodes.value.map((node) => [node.id, node]))
  const source = byId.get(current.prerequisite_id)
  const target = byId.get(current.mission_id)
  const visibleIds = new Set(visibleNodes.value.map((node) => node.id))
  return {
    sourceTitle: source?.title ?? `#${current.prerequisite_id.slice(0, 8)}`,
    targetTitle: target?.title ?? `#${current.mission_id.slice(0, 8)}`,
    targetId: current.mission_id,
    color: edgeStrokeColor(current, visibleIds),
    satisfied: current.is_satisfied,
    crossMilestone: current.cross_milestone,
  }
})

/** Distinct milestones in the visible graph, for the card-colour legend. */
const milestoneLegend = computed(() => {
  const entries = new Map<string, { id: string; name: string; color: string; count: number }>()
  for (const node of visibleNodes.value) {
    const key = node.milestone_id ?? ''
    const entry = entries.get(key)
    if (entry) {
      entry.count += 1
    } else {
      entries.set(key, {
        id: key,
        name: milestoneLabel(node.milestone_name),
        color: milestoneColor(node.milestone_id),
        count: 1,
      })
    }
  }
  return [...entries.values()].sort((a, b) => {
    if (a.id === b.id) return 0
    if (a.id === '') return 1
    if (b.id === '') return -1
    return a.name.localeCompare(b.name, 'zh')
  })
})

// --- requests ------------------------------------------------------------- //
let requestSeq = 0

function baseParams(): QueryParams {
  const current = filters.value
  return {
    ...extraFilters.value,
    date_from: dateFrom.value || undefined,
    date_to: dateTo.value || undefined,
    design_element: current.design_element || undefined,
    q: current.q || undefined,
    milestone: current.milestone || undefined,
    status: current.status || undefined,
    type: current.type || undefined,
    priority: current.priority || undefined,
    assignee: current.assignee || undefined,
    reviewer: current.reviewer || undefined,
    blocked: current.blocked || undefined,
    revalidation: current.revalidation || undefined,
  }
}

async function loadOverview(seq: number) {
  const data = await getWorkspaceOverview({
    ...baseParams(),
    column_limit: columnLimit.value,
  })
  // A newer request (e.g. the close that clears the focus and its scope) owns
  // the state: a slow response must never write back an older view.
  if (seq !== requestSeq) return
  overview.value = data
  lastRefreshed.value = data.generated_at
}

async function loadGraph(seq: number) {
  const focus = selectedId.value
  const scoped = relatedOnly.value && !!focus
  const data = await getWorkspaceGraph({
    ...baseParams(),
    date_from: dateFrom.value || undefined,
    date_to: dateTo.value || undefined,
    scope: scoped ? 'mission' : 'team',
    focus: focus || undefined,
    expand: scoped ? 'all' : focus ? expandMode.value : 'none',
    direction: direction.value,
    include_parent: showParentRelations.value ? 'true' : undefined,
    context: scoped ? 'false' : 'true',
    depth: 5,
  })
  if (seq !== requestSeq) return
  graph.value = data
  if (data.meta.date_from && data.meta.date_to) {
    dateFrom.value = data.meta.date_from; dateTo.value = data.meta.date_to
    syncUrl()
  }
  selectedEdge.value = null
  lastRefreshed.value = data.generated_at
  // A task selected through the URL can sit inside a collapsed subtree: expand
  // its ancestors so the initial focus always lands on something visible.
  if (showParentRelations.value && selectedId.value) {
    const view = groupByParent(
      data.nodes,
      data.edges,
      data.parent_edges,
      collapsedParents.value,
    )
    if (view.hidden.has(selectedId.value)) {
      collapsedParents.value = revealPath(
        data.nodes,
        data.parent_edges,
        collapsedParents.value,
        selectedId.value,
      )
    }
  }
}

async function reload(options: { fitGraph?: boolean } = {}) {
  const seq = ++requestSeq
  loading.value = true
  error.value = ''
  try {
    if (view.value === 'overview') {
      await loadOverview(seq)
      if (seq !== requestSeq) return
    } else {
      await loadGraph(seq)
      if (seq !== requestSeq) return
      await nextTick()
      if (seq !== requestSeq) return
      if (selectedId.value) graphRef.value?.locate(selectedId.value)
      else if (options.fitGraph) graphRef.value?.fit()
    }
  } catch (err) {
    if (seq !== requestSeq) return
    error.value = err instanceof ApiException ? err.message : '加载失败，请重试'
    ElMessage.error(error.value)
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

// --- URL <-> state -------------------------------------------------------- //
function applyQuery() {
  const query = route.query
  savedViewId.value = readParam(query.saved_view)
  extraFilters.value = {}
  for (const key of ['creator', 'tag', 'parent', 'production_batch', 'ordering']) {
    if (query[key] && !(key === 'parent' && query[key] === 'false')) extraFilters.value[key] = query[key] as string | string[]
  }
  dateFrom.value = readParam(query.date_from)
  dateTo.value = readParam(query.date_to)
  dateZoom.value = readParam(query.zoom) === 'week' ? 'week' : 'day'
  view.value = readParam(query.view) === 'graph' ? 'graph' : 'overview'
  selectedId.value = readParam(query.selected) || null
  const limit = Number(readParam(query.limit))
  columnLimit.value = Number.isFinite(limit) && limit > 0 ? limit : 20
  relatedOnly.value = readParam(query.related) === 'true'
  relationListMode.value = readParam(query.relations) === 'true'
  showParentRelations.value = readParam(query.show_parent) !== 'false' && readParam(query.parent) !== 'false'
  expandMode.value = readParam(query.expand) === 'all' ? 'all' : 'one'
  const dir = readParam(query.direction)
  direction.value = dir === 'upstream' || dir === 'downstream' ? dir : 'both'

  const next = emptyFilters()
  next.design_element = readParam(query.design_element)
  next.q = readParam(query.q)
  next.milestone = readParam(query.milestone)
  next.status = (readParam(query.status) as WorkspaceFilters['status']) || ''
  next.type = (readParam(query.type) as WorkspaceFilters['type']) || ''
  next.priority = (readParam(query.priority) as WorkspaceFilters['priority']) || ''
  next.assignee = readParam(query.assignee)
  next.reviewer = readParam(query.reviewer)
  const blocked = readParam(query.blocked)
  next.blocked = blocked === 'true' || blocked === 'false' ? blocked : ''
  next.revalidation = ['true', 'false'].includes(readParam(query.revalidation)) ? readParam(query.revalidation) as 'true' | 'false' : ''
  filters.value = next
}

function queryFromState(): Record<string, string> {
  const out: Record<string, string> = {}
  if (savedViewId.value) out.saved_view = savedViewId.value
  for (const [key, value] of Object.entries(extraFilters.value)) if (value !== undefined) out[key] = Array.isArray(value) ? value.join(',') : String(value)
  const set = (key: string, value: string) => {
    if (value) out[key] = value
  }
  if (view.value === 'graph') out.view = 'graph'
  set('date_from', dateFrom.value)
  set('date_to', dateTo.value)
  if (dateZoom.value !== 'day') set('zoom', dateZoom.value)
  const current = filters.value
  set('design_element', current.design_element || '')
  set('q', current.q)
  set('milestone', current.milestone)
  set('status', current.status)
  set('type', current.type)
  set('priority', current.priority)
  set('assignee', current.assignee)
  set('reviewer', current.reviewer)
  set('blocked', current.blocked)
  set('revalidation', current.revalidation)
  set('selected', selectedId.value ?? '')
  if (columnLimit.value !== 20) set('limit', String(columnLimit.value))
  if (relatedOnly.value) set('related', 'true')
  if (relationListMode.value) set('relations', 'true')
  if (!showParentRelations.value) set('show_parent', 'false')
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

// 浏览器前进/后退或外部导航也必须使旧请求失效；本页自己的 URL 同步不重复加载。
watch(() => route.query, query => {
  const current = queryFromState()
  if (Object.keys(current).length === Object.keys(query).length &&
      Object.entries(current).every(([key, value]) => readParam(query[key]) === value)) return
  applyQuery()
  void reload({ fitGraph: view.value === 'graph' })
})

// --- interactions --------------------------------------------------------- //
function onFilterChange() {
  columnLimit.value = 20
  syncUrl()
  void reload({ fitGraph: view.value === 'graph' })
}

function onQuickToggle(key: QuickKey) {
  const current = filters.value
  if (key === 'mine') {
    current.assignee = current.assignee === 'me' ? '' : 'me'
  } else if (key === 'blocked') {
    current.blocked = current.blocked === 'true' ? '' : 'true'
  } else if (key === 'review') {
    if (onlyReview.value) {
      current.reviewer = ''
      current.status = ''
    } else {
      current.reviewer = 'me'
      current.status = 'Submitted'
    }
  } else if (key === 'revalidation') {
    current.revalidation = current.revalidation === 'true' ? '' : 'true'
  }
  onFilterChange()
}

function switchView(next: 'overview' | 'graph') {
  if (view.value === next) return
  view.value = next
  syncUrl()
  void reload({ fitGraph: next === 'graph' })
}

function revealHidden(id: string) {
  if (!graph.value || !collapsedParents.value.size) return
  collapsedParents.value = revealPath(
    graphNodes.value,
    graph.value.parent_edges,
    collapsedParents.value,
    id,
  )
}

function onSelect(id: string) {
  revealHidden(id)
  selectedId.value = id
  drawerOpen.value = true
  syncUrl()
}

function onFocus(id: string) {
  revealHidden(id)
  selectedId.value = id
  drawerOpen.value = false
  if (view.value !== 'graph') {
    view.value = 'graph'
    syncUrl()
    void reload({ fitGraph: true })
  } else {
    syncUrl()
    graphRef.value?.locate(id)
  }
}

/** Collapse or expand a parent's subtasks in the graph. */
function onToggleChildren(id: string) {
  const next = new Set(collapsedParents.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsedParents.value = next
  // A collapsed subtree hides the selection: clear it instead of pointing at a
  // card that is no longer on the canvas.
  if (selectedId.value && graph.value) {
    const view = groupByParent(
      graphNodes.value,
      graphEdges.value,
      graph.value.parent_edges,
      next,
    )
    if (view.hidden.has(selectedId.value)) {
      selectedId.value = null
      drawerOpen.value = false
      selectedEdge.value = null
      syncUrl()
    }
  }
}

function onGraphOptionChange() {
  syncUrl()
  void reload()
}

function onAllUpstream() {
  direction.value = 'upstream'
  expandMode.value = 'all'
  onGraphOptionChange()
}

function onAllDownstream() {
  direction.value = 'downstream'
  expandMode.value = 'all'
  onGraphOptionChange()
}

function onToggleRelated() {
  relatedOnly.value = !relatedOnly.value
  onGraphOptionChange()
}

function onLoadMore() {
  columnLimit.value += 20
  syncUrl()
  void reload()
}

function onDrawerChanged() {
  notifyChanged()
  void reload()
}

/**
 * Closing the drawer clears the mission focus: `selectedId`, the selected edge,
 * the highlight/dimming and the upstream/downstream summary all go away, and the
 * `selected` URL parameter is dropped. Filter, view mode, parent display/collapse
 * state and the canvas viewport are untouched.
 *
 * "只看相关" is a focus-scoped view, so it exits too and the team-wide graph is
 * fetched again — otherwise the canvas would stay cropped to the mission that was
 * just closed. The request generation makes sure an in-flight focused request
 * cannot write the old focus/scope back.
 *
 * A *programmatic* close (opening another mission from the drawer via `focus`)
 * flips `drawerOpen` without emitting `close`, so this handler never clears the
 * newly chosen focus.
 */
function onDrawerClose() {
  const wasScoped = relatedOnly.value
  drawerOpen.value = false
  selectedId.value = null
  selectedEdge.value = null
  relatedOnly.value = false
  syncUrl()
  if (wasScoped && view.value === 'graph') void reload()
}

function applyDates() {
  if (!!dateFrom.value !== !!dateTo.value) { ElMessage.warning('请同时选择开始和结束日期'); return }
  syncUrl(); void reload({ fitGraph: true })
}
function openPagedList() {
  const query = { ...baseParams(), date_from: dateFrom.value, date_to: dateTo.value, status: filters.value.status || 'all' }
  void router.push({ name: 'square', query: Object.fromEntries(Object.entries(query).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])) })
}
const savedQuery = computed(() => ({ ...baseParams(), zoom: dateZoom.value }))
function applyAllFilters(query: QueryParams) {
  const next: Record<string, string | string[]> = { view: view.value }
  for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== null && value !== '') next[key] = Array.isArray(value) ? value.map(String) : String(value)
  if (savedViewId.value) next.saved_view = savedViewId.value
  if (dateZoom.value === 'week') next.zoom = 'week'
  void router.push({ path: '/workspace', query: next })
}
function removeSavedFilter(key: string) {
  const next = { ...baseParams() }
  delete next[key]
  if (key.startsWith('date_')) { delete next.date_from; delete next.date_to }
  applyAllFilters(next)
}
function refresh() {
  void reload({ fitGraph: view.value === 'graph' })
}

const formatTime = (value: string) => (value ? new Date(value).toLocaleTimeString() : '')

// --- low-frequency polling ------------------------------------------------ //
const POLL_MS = 30_000
let pollTimer: ReturnType<typeof setInterval> | undefined

function onWindowFocus() {
  void reload()
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') void reload()
}

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
  pollTimer = setInterval(() => {
    if (document.visibilityState === 'visible') void reload()
  }, POLL_MS)
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('focus', onWindowFocus)
})

onBeforeUnmount(() => {
  requestSeq += 1
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('focus', onWindowFocus)
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
          <el-radio-button value="graph">甘特图</el-radio-button>
        </el-radio-group>
        <el-button @click="refresh">刷新</el-button>
        <el-button type="primary" @click="router.push({ name: 'mission-create' })">
          发布任务
        </el-button>
      </div>
    </div>

    <SavedViewsBar :query="savedQuery" :target="view === 'graph' ? 'Gantt' : 'Overview'" @remove="removeSavedFilter" @opened="selectedId = null; drawerOpen = false; collapsedParents = new Set(); reload({ fitGraph: true })" />
    <MissionQueryForm :query="savedQuery" @apply="applyAllFilters" />
    <WorkspaceFilterBar
      :filters="filters"
      :members="members"
      :milestone-options="milestoneOptions"
      :only-mine="onlyMine"
      :only-blocked="onlyBlocked"
      :only-review="onlyReview"
      :only-revalidation="onlyRevalidation"
      @change="onFilterChange"
      @toggle="onQuickToggle"
    />

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
      <span class="meta">（仅统计当前筛选命中的任务，不含依赖上下文）</span>
    </div>

    <div v-if="view === 'graph'" class="workspace__graph-options">
      <el-date-picker v-model="dateFrom" type="date" value-format="YYYY-MM-DD" placeholder="范围开始" aria-label="甘特图范围开始" />
      <el-date-picker v-model="dateTo" type="date" value-format="YYYY-MM-DD" placeholder="范围结束" aria-label="甘特图范围结束" />
      <el-button @click="applyDates">应用日期</el-button>
      <el-radio-group v-model="dateZoom" @change="syncUrl"><el-radio-button value="day">日</el-radio-button><el-radio-button value="week">周</el-radio-button></el-radio-group>
    </div>
    <div v-if="view === 'graph'" class="workspace__graph-options">
      <span class="meta">选中任务：{{ selectedId ? `#${selectedId.slice(0, 8)}` : '未选择' }}</span>
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
      <el-button size="small" :disabled="!selectedId" @click="onAllUpstream">全部上游</el-button>
      <el-button size="small" :disabled="!selectedId" @click="onAllDownstream">全部下游</el-button>
      <el-checkbox
        :model-value="relatedOnly"
        :disabled="!selectedId"
        @change="onToggleRelated"
      >
        只看相关
      </el-checkbox>
      <el-button v-if="relatedOnly" link type="primary" size="small" @click="onToggleRelated">
        返回完整范围
      </el-button>
      <el-checkbox v-model="showParentRelations" @change="onGraphOptionChange">
        显示父子任务关系
      </el-checkbox>
      <el-checkbox v-model="relationListMode" @change="syncUrl">关系列表</el-checkbox>
      <span class="meta">横轴为计划日期；依赖连接结束端，下游不得早于前置结束</span>
    </div>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="workspace__error">
      {{ error }}
      <el-button link type="primary" @click="refresh">重试</el-button>
    </el-alert>

    <el-alert
      v-if="view === 'graph' && graphMeta && !graphMeta.relationships_complete"
      type="warning"
      :closable="false"
      show-icon
      class="workspace__error"
    >
      关系加载不完整（{{ graphMeta.truncation_reasons.map((r) => truncationLabels[r] ?? r).join('、') || '存在未加载的前置任务' }}），
      请缩小筛选或聚焦某个任务后再查看上下游。
    </el-alert>

    <el-alert
      v-if="graphHasCycle"
      type="warning"
      :closable="false"
      show-icon
      class="workspace__error"
      data-test="graph-cycle"
    >
      依赖关系存在环（可能由折叠合并产生）；请展开相关子任务核对真实关系。
    </el-alert>

    <div v-loading="loading" class="workspace__main">
      <template v-if="view === 'overview'">
        <MilestoneBoard
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
          <el-alert
            v-if="selectedRelations"
            type="info"
            :closable="false"
            class="workspace__relations-text"
          >
            <div>选中任务的全部上游：{{ selectedRelations.upstream }}</div>
            <div>选中任务的全部下游：{{ selectedRelations.downstream }}</div>
          </el-alert>

          <el-alert
            v-if="selectedEdgeInfo"
            type="info"
            :closable="true"
            class="workspace__edge-info"
            @close="selectedEdge = null"
          >
            <div class="workspace__edge-line">
              <span
                class="workspace__edge-swatch"
                :style="{ background: selectedEdgeInfo.color }"
              />
              来源前置任务：{{ selectedEdgeInfo.sourceTitle }} → 依赖任务：{{
                selectedEdgeInfo.targetTitle
              }}
              · {{ selectedEdgeInfo.satisfied ? '已满足' : '尚未满足' }}
              <template v-if="selectedEdgeInfo.crossMilestone"> · 跨里程碑</template>
            </div>
            <el-button link type="primary" size="small" @click="onFocus(selectedEdgeInfo.targetId)">
              打开依赖任务
            </el-button>
          </el-alert>

          <DependencyGraph
            ref="graphRef"
            :date-from="graph.meta.date_from"
            :date-to="graph.meta.date_to"
            :today="graph.meta.today"
            :zoom="dateZoom"
            :nodes="visibleNodes"
            :edges="visibleEdges"
            :selected-id="selectedId"
            :grouping="grouped"
            :emphasis-ids="emphasisIds"
            @select="onSelect"
            @focus="onFocus"
            @edge-select="selectedEdge = $event"
            @toggle-collapse="onToggleChildren"
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
            <el-tag v-if="graph.meta.relationships_complete" type="success" size="small">
              关系完整
            </el-tag>
            <el-tag v-else type="warning" size="small">关系不完整</el-tag>
            <el-tag v-if="grouped && grouped.hidden.size" type="info" size="small">
              已折叠 {{ grouped.hidden.size }} 个子任务（依赖已合并到父任务）
            </el-tag>
          </div>

          <div class="workspace__edge-legend">
            <span class="meta">
              依赖线颜色对应前置 Mission（同一前置的线同色，与卡片里程碑颜色是两套含义）；实线=已满足，虚线=尚未满足
            </span>
          </div>

          <div v-if="milestoneLegend.length" class="workspace__milestone-legend">
            <span class="meta">卡片颜色（所属里程碑）：</span>
            <span
              v-for="item in milestoneLegend"
              :key="item.id || 'none'"
              class="workspace__milestone-item"
            >
              <span class="workspace__milestone-swatch" :style="{ background: item.color }" />
              {{ item.name }}（{{ item.count }}）
            </span>
          </div>
        </template>
      </template>
    </div>

    <section v-if="view === 'graph' && graph" class="workspace__date-list">
      <p v-if="grouped?.hidden.size" class="meta">折叠后的依赖线是隐藏任务关系的汇总，父任务日期不代表全部子任务排期；请展开核对。</p>
      <p class="meta">里程碑目标：<span v-for="item in [...new Map(graphNodes.filter(n => n.milestone_id).map(n => [n.milestone_id, n])).values()]" :key="item.id">{{ item.milestone_name }} {{ item.milestone_due_date ?? '未设日期' }}；</span></p>
      <details><summary>已加载任务的日期与风险列表（支持键盘打开详情）</summary>
        <el-table :data="graphNodes" empty-text="没有匹配任务">
          <el-table-column label="任务"><template #default="{ row }"><el-button link type="primary" @click="onSelect(row.id)">{{ row.title }}</el-button></template></el-table-column>
          <el-table-column label="状态与认领者"><template #default="{ row }"><StatusTag :status="row.status" /> {{ row.assignee?.display_name ?? '未认领' }}<span v-if="row.is_blocked"> · 受阻</span></template></el-table-column>
          <el-table-column label="日期与风险"><template #default="{ row }"><MissionSchedule :mission="row" /><span v-if="row.unloaded_prerequisite_count">{{ row.unloaded_prerequisite_count }} 项前置未加载，请打开详情查看</span></template></el-table-column>
        </el-table>
      </details>
      <el-button @click="openPagedList">在分页任务列表中查看当前范围</el-button>
    </section>
    <div class="workspace__legend">
      <span class="meta">状态：</span>
      <el-tag size="small" type="info">待认领</el-tag>
      <el-tag size="small" type="primary">进行中</el-tag>
      <el-tag size="small" type="warning">待验收</el-tag>
      <el-tag size="small" type="success">已完成</el-tag>
      <el-tag size="small" type="danger">已取消</el-tag>
      <span class="meta">
        · 依赖箭头：前置结束端 → 下游结束端；同日前置可先完成。线色对应前置 Mission，实线=已满足，虚线=等待；任务条颜色表示里程碑。未排期位置不表示日期；缺一端时仅显示单端标记，折叠后依赖合并到父任务。
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
.workspace__relations-text {
  margin-bottom: 8px;
}
.workspace__edge-info {
  margin-bottom: 8px;
}
.workspace__edge-line {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.workspace__edge-swatch {
  width: 14px;
  height: 4px;
  border-radius: 2px;
  flex: none;
}
.workspace__edge-legend {
  margin-top: 8px;
}
.workspace__main {
  min-height: 200px;
}
.workspace__graph-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.workspace__milestone-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  font-size: 12px;
  color: #6b7280;
}
.workspace__milestone-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.workspace__milestone-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex: none;
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
