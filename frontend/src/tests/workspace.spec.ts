import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

// --- Vue Flow is stubbed: these tests cover our mapping/markup, not the lib. //
const flowMock = vi.hoisted(() => {
  const handlers: Record<string, ((arg: unknown) => void)[]> = {}
  const register = (name: string) => (fn?: (arg: unknown) => void) => {
    if (fn) (handlers[name] ||= []).push(fn)
  }
  return {
    handlers,
    register,
    fitView: vi.fn().mockResolvedValue(true),
    setCenter: vi.fn().mockResolvedValue(true),
    findNode: vi.fn().mockReturnValue(undefined),
  }
})

vi.mock('@vue-flow/core', () => ({
  VueFlow: {
    name: 'VueFlow',
    props: {
      nodes: { type: Array, default: () => [] },
      edges: { type: Array, default: () => [] },
    },
    template: `
      <div class="vf-stub">
        <div v-for="n in nodes" :key="n.id" class="vf-node">
          <slot name="node-mission" :data="n.data" />
        </div>
      </div>`,
  },
  Handle: { template: '<span class="vf-handle" />' },
  Position: { Left: 'left', Right: 'right' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
  useVueFlow: () => ({
    fitView: flowMock.fitView,
    setCenter: flowMock.setCenter,
    findNode: flowMock.findNode,
    onNodesInitialized: flowMock.register('nodesInitialized'),
    onNodeClick: flowMock.register('nodeClick'),
    onEdgeClick: flowMock.register('edgeClick'),
  }),
}))

vi.mock('@vue-flow/controls', () => ({ Controls: { template: '<div class="vf-controls" />' } }))

import { getWorkspaceGraph, getWorkspaceOverview } from '../api/workspace'
import type { MissionStatus, WorkspaceEdge, WorkspaceGroup, WorkspaceNode } from '../api/types'
import { computeDagreLayout, graphStructureSignature, useDagreLayout } from '../composables/useDagreLayout'
import DependencyGraph from '../components/DependencyGraph.vue'
import MilestoneBoard from '../components/MilestoneBoard.vue'
import WorkspaceMissionCard from '../components/WorkspaceMissionCard.vue'
import {
  buildDependencyEdges,
  buildMissionNodes,
  NODE_WIDTH,
} from '../workspace/dto'
import { collectRelated, directRelations } from '../workspace/dependencyTraversal'
import {
  milestoneColor,
  UNASSIGNED_MILESTONE_COLOR,
} from '../workspace/milestoneColor'

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function node(id: string, overrides: Partial<WorkspaceNode> = {}): WorkspaceNode {
  return {
    id,
    title: `任务 ${id}`,
    type: 'Task',
    priority: 'P2',
    status: 'Open',
    creator: { id: 1, username: 'alice', display_name: 'Alice' },
    assignee: null,
    reviewer: null,
    parent_id: null,
    milestone_id: null,
    milestone_name: null,
    version: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    is_blocked: false,
    has_unresolved_prerequisites: false,
    requires_revalidation: false,
    needs_dependency_review: false,
    blocking_count: 0,
    unfinished_child_count: 0,
    reviewer_missing: false,
    milestone_closed: false,
    is_context: false,
    allowed_actions: [],
    ...overrides,
  }
}

const edge = (
  id: string,
  prerequisite: string,
  mission: string,
  overrides: Partial<WorkspaceEdge> = {},
): WorkspaceEdge => ({
  id,
  prerequisite_id: prerequisite,
  mission_id: mission,
  is_satisfied: false,
  cross_milestone: false,
  ...overrides,
})

const stubs = {
  'el-tag': { template: '<span><slot /></span>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-empty': { template: '<div />' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<div><slot /></div>' },
  'el-input': { template: '<input />' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': { template: '<div><slot /></div>' },
  'el-tooltip': { template: '<div><slot /></div>' },
  'el-checkbox': { template: '<label><slot /></label>' },
  'el-checkbox-button': { template: '<button><slot /></button>' },
  'el-alert': { template: '<div><slot /></div>' },
  'el-table': { template: '<div><slot /></div>' },
  'el-table-column': { template: '<div />' },
}

describe('workspace api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requests the overview with filters and column limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ groups: [], summary: {}, columns: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getWorkspaceOverview({ q: 'dash', milestone: 'none', blocked: 'true', column_limit: 40 })

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/workspace/overview/?q=dash&milestone=none&blocked=true&column_limit=40',
    )
  })

  it('requests the graph with scope, focus and direction', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ nodes: [], edges: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await getWorkspaceGraph({
      scope: 'mission',
      focus: 'm1',
      expand: 'all',
      direction: 'downstream',
      include_parent: 'true',
    })

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/workspace/graph/?scope=mission&focus=m1&expand=all&direction=downstream&include_parent=true',
    )
  })
})

describe('Dagre layout', () => {
  it('lays prerequisite ranks to the left of their dependents', () => {
    const nodes = [node('a'), node('b'), node('c'), node('d'), node('e')]
    const edges = [edge('1', 'a', 'c'), edge('2', 'b', 'c'), edge('3', 'c', 'd')]
    const { positions } = computeDagreLayout(nodes, edges)

    const a = positions.get('a')!
    const b = positions.get('b')!
    const c = positions.get('c')!
    const d = positions.get('d')!
    // Same rank shares an x; each dependent sits a full column to the right.
    expect(a.x).toBe(b.x)
    expect(c.x).toBeGreaterThan(a.x)
    expect(d.x).toBeGreaterThan(c.x)
    expect(d.x - c.x).toBeGreaterThan(NODE_WIDTH)
    // Isolated node still gets a position.
    expect(positions.get('e')).toBeTruthy()
  })

  it('converts Dagre centres to Vue Flow top-left coordinates', () => {
    const { positions, width } = computeDagreLayout([node('a')], [])
    const a = positions.get('a')!
    expect(Number.isFinite(a.x)).toBe(true)
    expect(Number.isFinite(a.y)).toBe(true)
    expect(width).toBeGreaterThanOrEqual(a.x + NODE_WIDTH)
  })

  it('only re-lays out when the structure changes, not on status refresh', () => {
    const nodes = [node('a'), node('b')]
    const edges = [edge('1', 'a', 'b')]
    const layout = useDagreLayout()

    expect(layout.update(nodes, edges)).toBe(true)
    const first = new Map(layout.positions.value)

    const refreshed = nodes.map((item) => ({ ...item, status: 'Done' as const, title: '新标题' }))
    expect(layout.update(refreshed, edges)).toBe(false)
    expect(layout.positions.value).toEqual(first)

    const withExtra = [...nodes, node('c')]
    expect(layout.update(withExtra, edges)).toBe(true)
    expect(layout.positions.value.size).toBe(3)
  })

  it('signs only structure, not titles or status', () => {
    const edges = [edge('1', 'a', 'b')]
    expect(graphStructureSignature([node('a'), node('b')], edges)).toBe(
      graphStructureSignature([node('a', { status: 'Done' }), node('b', { title: 'x' })], edges),
    )
  })
})

describe('dependency traversal', () => {
  const edges = [edge('1', 'a', 'c'), edge('2', 'b', 'c'), edge('3', 'c', 'd')]

  it('reports direct prerequisites and dependents', () => {
    const relations = directRelations('c', edges)
    expect([...relations.prerequisites].sort()).toEqual(['a', 'b'])
    expect([...relations.dependents]).toEqual(['d'])
  })

  it('walks upstream, downstream and both directions without loops', () => {
    expect(collectRelated('d', edges, 'upstream').sort()).toEqual(['a', 'b', 'c'])
    expect(collectRelated('a', edges, 'downstream').sort()).toEqual(['c', 'd'])
    expect(collectRelated('c', edges, 'both').sort()).toEqual(['a', 'b', 'd'])
    expect(collectRelated('a', edges, 'upstream')).toEqual([])
  })
})

describe('DTO adapter', () => {
  it('maps dependency edges with arrow markers and state classes', () => {
    const edges = [
      edge('1', 'a', 'c', { is_satisfied: true }),
      edge('2', 'b', 'c', { is_satisfied: false, cross_milestone: true }),
    ]
    const flowEdges = buildDependencyEdges(edges, null)
    expect(flowEdges[0].source).toBe('a')
    expect(flowEdges[0].target).toBe('c')
    expect(flowEdges[0].markerEnd).toBe('arrowclosed')
    expect(flowEdges[0].class).toContain('ws-edge--satisfied')
    expect(flowEdges[1].class).toContain('ws-edge--pending')
    // Cross-milestone edges are no longer labelled; the milestone is shown by
    // the node colour instead.
    expect(flowEdges[1].label).toBeUndefined()
  })

  it('maps nodes with selected/dimmed flags and keeps isolated nodes', () => {
    const positions = new Map([
      ['a', { x: 0, y: 0 }],
      ['e', { x: 0, y: 200 }],
    ])
    const flowNodes = buildMissionNodes(
      [node('a'), node('e')],
      positions,
      new Set(['a']),
      'a',
    )
    expect(flowNodes).toHaveLength(2)
    expect(flowNodes[0].draggable).toBe(false)
    expect(flowNodes[0].data?.selected).toBe(true)
    expect(flowNodes[0].data?.dimmed).toBe(false)
    expect(flowNodes[1].data?.dimmed).toBe(true)
  })

  it('derives a stable milestone colour per node', () => {
    const first = buildMissionNodes([node('a', { milestone_id: 'm1' })], new Map(), null, null)
    const second = buildMissionNodes([node('b', { milestone_id: 'm1' })], new Map(), null, null)
    const other = buildMissionNodes([node('c', { milestone_id: 'm2' })], new Map(), null, null)
    const none = buildMissionNodes([node('d')], new Map(), null, null)
    expect(first[0].data?.color).toBe(milestoneColor('m1'))
    expect(second[0].data?.color).toBe(first[0].data?.color)
    expect(none[0].data?.color).toBe(UNASSIGNED_MILESTONE_COLOR)
    expect(other[0].data?.color).not.toBe(first[0].data?.color)
  })
})

describe('WorkspaceMissionCard', () => {
  it('shows unfinished prerequisites and children separately', () => {
    const wrapper = mount(WorkspaceMissionCard, {
      props: { node: node('a', { blocking_count: 2, unfinished_child_count: 1 }) },
      global: { stubs },
    })
    const text = wrapper.text()
    expect(text).toContain('前置未完成 2')
    expect(text).toContain('子任务未完成 1')
  })

  it('opens on Enter and emits select', async () => {
    const wrapper = mount(WorkspaceMissionCard, {
      props: { node: node('a') },
      global: { stubs },
    })
    await wrapper.find('.ws-card').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')?.[0]).toEqual(['a'])
  })

  it('applies the milestone colour only when one is provided', () => {
    const plain = mount(WorkspaceMissionCard, {
      props: { node: node('a') },
      global: { stubs },
    })
    expect(plain.find('.ws-card').classes()).not.toContain('ws-card--milestoned')
    expect(plain.find('.ws-card__swatch').exists()).toBe(false)

    const colored = mount(WorkspaceMissionCard, {
      props: { node: node('a', { milestone_name: '基础移动' }), milestoneColor: '#2563eb', compact: true },
      global: { stubs },
    })
    expect(colored.find('.ws-card').classes()).toContain('ws-card--milestoned')
    expect(colored.find('.ws-card').attributes('style')).toContain('--ws-milestone: #2563eb')
    expect(colored.find('.ws-card__swatch').attributes('title')).toContain('基础移动')
  })
})

describe('MilestoneBoard', () => {
  function groupFixture(): WorkspaceGroup {
    return {
      milestone: { id: 'm2', name: '首个可玩版本', status: 'Active', due_date: '2026-12-01' },
      is_unassigned: false,
      full_counts: { total: 3, effective_total: 2, done: 1, progress: 0.5 },
      full_counts_scope: 'milestone_all_visible',
      matched_counts: { Open: 2, InProgress: 0, Submitted: 0, Done: 0, Cancelled: 0 },
      matched_counts_scope: 'active_filters',
      matched_total: 2,
      loaded: { Open: 1, InProgress: 0, Submitted: 0, Done: 0, Cancelled: 0 },
      columns: {
        Open: [node('c', { title: '动画接入', status: 'Open', is_blocked: true })],
        InProgress: [],
        Submitted: [],
        Done: [],
        Cancelled: [],
      },
    }
  }

  const columns: MissionStatus[] = [
    'Open',
    'InProgress',
    'Submitted',
    'Done',
    'Cancelled',
  ]
  const columnLabels: Record<MissionStatus, string> = {
    Open: '待认领',
    InProgress: '进行中',
    Submitted: '待验收',
    Done: '已完成',
    Cancelled: '已取消',
  }

  it('renders milestone totals, matched counts and a load-more hint', () => {
    const wrapper = mount(MilestoneBoard, {
      props: {
        groups: [groupFixture()],
        columns,
        columnLabels,
        filtersActive: true,
        selectedId: null,
      },
      global: { stubs },
    })
    const text = wrapper.text()
    expect(text).toContain('首个可玩版本')
    expect(text).toContain('里程碑总计 1 / 2')
    expect(text).toContain('当前筛选 2 个')
    expect(text).toContain('动画接入')
    expect(text).toContain('已显示 1 / 2')
  })

  it('emits loadMore when a column is truncated', async () => {
    const wrapper = mount(MilestoneBoard, {
      props: {
        groups: [groupFixture()],
        columns,
        columnLabels,
        filtersActive: true,
        selectedId: null,
      },
      global: { stubs },
    })
    const button = wrapper.findAll('button').find((item) => item.text().includes('加载更多'))
    expect(button).toBeTruthy()
    await button!.trigger('click')
    expect(wrapper.emitted('loadMore')).toBeTruthy()
  })
})

describe('DependencyGraph', () => {
  it('renders every node, including isolated ones, and emits select', async () => {
    const wrapper = mount(DependencyGraph, {
      props: {
        nodes: [node('a'), node('b'), node('e', { title: '孤立任务' })],
        edges: [edge('1', 'a', 'b')],
      },
    })
    expect(wrapper.findAll('.vf-node')).toHaveLength(3)
    expect(wrapper.text()).toContain('孤立任务')

    await wrapper.findAll('.ws-card')[0].trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['a'])
  })

  it('forwards edge clicks with the original edge', async () => {
    const dependency = edge('1', 'a', 'b')
    const wrapper = mount(DependencyGraph, {
      props: { nodes: [node('a'), node('b')], edges: [dependency] },
    })
    const handler = flowMock.handlers.edgeClick?.at(-1)
    expect(handler).toBeTruthy()
    handler?.({ edge: { data: { edge: dependency } } })
    await flushPromises()
    expect(wrapper.emitted('edgeSelect')?.[0]).toEqual([dependency])
  })
})

describe('WorkspaceView', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders the page summary from the overview API', async () => {
    const overviewPayload = {
      generated_at: '2026-10-14T10:00:00Z',
      revision: 'r1',
      filters_active: false,
      column_limit: 20,
      columns: ['Open', 'Done'],
      column_labels: { Open: '待认领', Done: '已完成' },
      summary: {
        matched_total: 5,
        effective_total: 4,
        done: 2,
        blocked: 1,
        submitted: 1,
        requires_revalidation: 1,
      },
      groups: [],
    }
    const fetchMock = vi.fn((input: unknown) => {
      const target = String(input)
      if (target.startsWith('/api/members')) return Promise.resolve(jsonResponse([]))
      if (target.startsWith('/api/milestones')) {
        return Promise.resolve(
          jsonResponse({ count: 0, next: null, previous: null, results: [] }),
        )
      }
      if (target.startsWith('/api/workspace/overview')) {
        return Promise.resolve(jsonResponse(overviewPayload))
      }
      return Promise.resolve(jsonResponse({}))
    })
    vi.stubGlobal('fetch', fetchMock)

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/workspace', name: 'workspace', component: { template: '<div />' } },
        { path: '/missions/new', name: 'mission-create', component: { template: '<div />' } },
        { path: '/missions/:id', name: 'mission-detail', component: { template: '<div />' } },
      ],
    })
    router.push('/workspace')
    await router.isReady()

    const WorkspaceView = (await import('../views/WorkspaceView.vue')).default
    const wrapper = mount(WorkspaceView, {
      global: {
        plugins: [router],
        stubs: {
          ...stubs,
          MilestoneBoard: true,
          DependencyGraph: true,
          MissionDetailDrawer: true,
        },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('任务总数 5')
    expect(text).toContain('有效完成 2 / 4')
    expect(text).toContain('需复核 1')
    expect(text).toContain('上次刷新')
    wrapper.unmount()
  })
})
