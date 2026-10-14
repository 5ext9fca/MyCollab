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
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
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
import {
  computeGraphLayout,
  dependencyLevels,
  graphStructureSignature,
  useGraphLayout,
  GRAPH_H_GAP,
  GRAPH_V_GAP,
} from '../composables/useGraphLayout'
import DependencyGraph from '../components/DependencyGraph.vue'
import MilestoneBoard from '../components/MilestoneBoard.vue'
import WorkspaceMissionCard from '../components/WorkspaceMissionCard.vue'
import { buildDependencyEdges, buildMissionNodes, NODE_HEIGHT, NODE_WIDTH } from '../workspace/dto'
import { DEPENDENCY_SOURCE_HANDLE, DEPENDENCY_TARGET_HANDLE } from '../workspace/dto'
import { collectRelated, directRelations } from '../workspace/dependencyTraversal'
import { buildForest, groupByParent, revealPath } from '../workspace/parentGrouping'
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

describe('layered graph layout', () => {
  it('places every dependent fully below all of its prerequisites', () => {
    const nodes = [node('a'), node('b'), node('c'), node('d'), node('e')]
    const edges = [edge('3', 'c', 'd'), edge('1', 'a', 'c'), edge('2', 'b', 'c')]
    const { positions, levels } = computeGraphLayout(nodes, edges)

    const a = positions.get('a')!
    const b = positions.get('b')!
    const c = positions.get('c')!
    const d = positions.get('d')!
    expect(levels.get('a')).toBe(0)
    expect(levels.get('b')).toBe(0)
    expect(levels.get('c')).toBe(1)
    expect(levels.get('d')).toBe(2)
    expect(a.y).toBe(b.y)
    // The whole card, not just its centre, sits below the prerequisites.
    expect(c.y).toBeGreaterThanOrEqual(a.y + NODE_HEIGHT)
    expect(c.y).toBeGreaterThanOrEqual(b.y + NODE_HEIGHT)
    expect(d.y).toBeGreaterThanOrEqual(c.y + NODE_HEIGHT)
    // Isolated node still gets a position.
    expect(positions.get('e')).toBeTruthy()
  })

  it('lays out top to bottom with a fixed row pitch', () => {
    const nodes = [node('a'), node('b')]
    const { positions } = computeGraphLayout(nodes, [edge('1', 'a', 'b')])
    expect(positions.get('b')!.y - positions.get('a')!.y).toBe(NODE_HEIGHT + GRAPH_V_GAP)
  })

  it('does not depend on the edge array order', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const first = computeGraphLayout(nodes, [edge('1', 'a', 'c'), edge('2', 'b', 'c')])
    const second = computeGraphLayout(nodes, [edge('2', 'b', 'c'), edge('1', 'a', 'c')])
    expect(second.positions).toEqual(first.positions)
  })

  it('puts a child one column right of its parent on the same row', () => {
    const nodes = [node('p'), node('a'), node('b')]
    const childrenOf = new Map([['p', ['a', 'b']]])
    const { positions } = computeGraphLayout(nodes, [], { childrenOf })
    const p = positions.get('p')!
    const a = positions.get('a')!
    const b = positions.get('b')!
    expect(a.y).toBe(p.y)
    expect(b.y).toBe(p.y)
    expect(a.x).toBe(p.x + NODE_WIDTH + GRAPH_H_GAP)
    expect(b.x).toBeGreaterThan(a.x)
  })

  it('lets dependency levels win over parent/child alignment', () => {
    const nodes = [node('p'), node('a'), node('b'), node('c')]
    const edges = [edge('1', 'a', 'b'), edge('2', 'b', 'c')]
    const childrenOf = new Map([['p', ['a']], ['a', ['b']], ['b', ['c']]])
    const { positions } = computeGraphLayout(nodes, edges, { childrenOf })
    const p = positions.get('p')!
    const a = positions.get('a')!
    const b = positions.get('b')!
    const c = positions.get('c')!
    expect(a.x).toBeGreaterThan(p.x)
    expect(a.y).toBe(p.y)
    expect(b.y).toBeGreaterThanOrEqual(a.y + NODE_HEIGHT)
    expect(c.y).toBeGreaterThanOrEqual(b.y + NODE_HEIGHT)
    expect(b.x).toBeGreaterThan(a.x)
    expect(c.x).toBeGreaterThan(b.x)
  })

  it('keeps a child inside its parent band and below external prerequisites', () => {
    const nodes = [node('p'), node('a'), node('x'), node('y')]
    const edges = [edge('1', 'x', 'a'), edge('2', 'y', 'a'), edge('3', 'x', 'y')]
    const childrenOf = new Map([['p', ['a']]])
    const { positions } = computeGraphLayout(nodes, edges, { childrenOf })
    const p = positions.get('p')!
    const a = positions.get('a')!
    const x = positions.get('x')!
    const y = positions.get('y')!
    expect(a.y).toBeGreaterThanOrEqual(x.y + NODE_HEIGHT)
    expect(a.y).toBeGreaterThanOrEqual(y.y + NODE_HEIGHT)
    // The direct child stays one column right of its parent, however deep it is.
    expect(a.x).toBe(p.x + NODE_WIDTH + GRAPH_H_GAP)
  })

  it('never overlaps cards of different families on the same row', () => {
    const nodes = [node('p'), node('a'), node('q'), node('r')]
    const childrenOf = new Map([['p', ['a']]])
    const { positions } = computeGraphLayout(nodes, [], { childrenOf })
    for (const [id, pos] of positions) {
      for (const [other, otherPos] of positions) {
        if (id === other || pos.y !== otherPos.y) continue
        expect(Math.abs(pos.x - otherPos.x)).toBeGreaterThanOrEqual(NODE_WIDTH + GRAPH_H_GAP)
      }
    }
  })

  it('reserves a family region so other cards cannot intrude', () => {
    const nodes = [node('p'), node('a'), node('z'), node('x'), node('y')]
    const edges = [edge('1', 'z', 'a'), edge('2', 'x', 'y')]
    const childrenOf = new Map([['p', ['a']]])
    const { positions } = computeGraphLayout(nodes, edges, { childrenOf })
    const p = positions.get('p')!
    const a = positions.get('a')!
    expect(a.y).toBeGreaterThan(p.y)
    // p's region spans every row and column its visible descendants use.
    const box = {
      left: Math.min(p.x, a.x),
      right: Math.max(p.x, a.x) + NODE_WIDTH,
      top: p.y,
      bottom: a.y + NODE_HEIGHT,
    }
    for (const [id, pos] of positions) {
      if (id === 'p' || id === 'a') continue
      const intrudes =
        pos.x < box.right &&
        pos.x + NODE_WIDTH > box.left &&
        pos.y < box.bottom &&
        pos.y + NODE_HEIGHT > box.top
      expect(intrudes, `${id} must stay outside p's family region`).toBe(false)
    }
  })

  it('reports a dependency cycle instead of drawing reversed edges', () => {
    const nodes = [node('a'), node('b')]
    const { hasCycle, positions } = computeGraphLayout(nodes, [
      edge('1', 'a', 'b'),
      edge('2', 'b', 'a'),
    ])
    expect(hasCycle).toBe(true)
    expect(Number.isFinite(positions.get('a')!.x)).toBe(true)
    expect(Number.isFinite(positions.get('b')!.y)).toBe(true)
    expect(dependencyLevels(['a', 'b'], []).hasCycle).toBe(false)
  })

  it('only re-lays out when the structure changes, not on a status refresh', () => {
    const nodes = [node('p'), node('c')]
    const childrenOf = new Map([['p', ['c']]])
    const layout = useGraphLayout()

    expect(layout.update(nodes, [], { childrenOf })).toBe(true)
    const first = new Map(layout.positions.value)

    const refreshed = nodes.map((item) => ({ ...item, status: 'Done' as const, title: '新标题' }))
    expect(layout.update(refreshed, [], { childrenOf })).toBe(false)
    expect(layout.positions.value).toEqual(first)

    // Collapsing the family is a structure change and moves the canvas.
    expect(layout.update([node('p')], [], { childrenOf: new Map([['p', []]]) })).toBe(true)
    expect(layout.positions.value.size).toBe(1)
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
    // The graph reads top to bottom, so edges leave the bottom and enter the top.
    expect(flowEdges[0].sourceHandle).toBe(DEPENDENCY_SOURCE_HANDLE)
    expect(flowEdges[0].targetHandle).toBe(DEPENDENCY_TARGET_HANDLE)
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

  it('collapses subtasks through the toggle without selecting the card', async () => {
    const wrapper = mount(WorkspaceMissionCard, {
      props: { node: node('p'), compact: true, descendantCount: 3, collapsed: false },
      global: { stubs },
    })
    const toggle = wrapper.find('.ws-card__toggle')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('子任务 3')
    await toggle.trigger('click')
    expect(wrapper.emitted('toggleChildren')?.[0]).toEqual(['p'])
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('hints that a collapsed parent merged its dependencies', () => {
    const wrapper = mount(WorkspaceMissionCard, {
      props: { node: node('p'), compact: true, descendantCount: 2, collapsed: true },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('依赖已合并')
  })

  it('shows no subtask toggle in board mode', () => {
    const wrapper = mount(WorkspaceMissionCard, {
      props: { node: node('p'), descendantCount: 3 },
      global: { stubs },
    })
    expect(wrapper.find('.ws-card__toggle').exists()).toBe(false)
  })

  it('marks a nested subtask card in the graph', () => {
    const nested = mount(WorkspaceMissionCard, {
      props: { node: node('a'), compact: true, depth: 1 },
      global: { stubs },
    })
    expect(nested.find('.ws-card__depth').exists()).toBe(true)
    expect(nested.find('.ws-card').attributes('aria-label')).toContain('子任务')

    const root = mount(WorkspaceMissionCard, {
      props: { node: node('a'), compact: true, depth: 0 },
      global: { stubs },
    })
    expect(root.find('.ws-card__depth').exists()).toBe(false)
  })
})

describe('parent/child grouping', () => {
  const parentEdges = [
    { parent_id: 'p', child_id: 'c1' },
    { parent_id: 'p', child_id: 'c2' },
  ]

  it('ignores parents outside the loaded set and self references', () => {
    const forest = buildForest([node('a'), node('b')], [
      { parent_id: 'ghost', child_id: 'a' },
      { parent_id: 'a', child_id: 'a' },
    ])
    expect(forest.parentOf.size).toBe(0)
    expect(forest.roots).toEqual(['a', 'b'])
  })

  it('refuses an edge that would close a parent/child cycle', () => {
    const forest = buildForest([node('a'), node('b')], [
      { parent_id: 'a', child_id: 'b' },
      { parent_id: 'b', child_id: 'a' },
    ])
    expect(forest.parentOf.get('b')).toBe('a')
    expect(forest.parentOf.has('a')).toBe(false)
    expect(forest.roots).toEqual(['a'])
  })

  it('keeps the visible parent/child structure and the children dependencies', () => {
    const nodes = [node('p'), node('c1'), node('c2'), node('x')]
    const edges = [
      edge('1', 'x', 'c1'),
      edge('2', 'x', 'c2'),
      edge('3', 'c1', 'c2'),
    ]
    const view = groupByParent(nodes, edges, parentEdges, new Set())

    expect(view.nodes.map((item) => item.id)).toEqual(['p', 'c1', 'c2', 'x'])
    expect(view.childCount.get('p')).toBe(2)
    expect(view.descendantCount.get('p')).toBe(2)
    expect(view.childrenOf.get('p')).toEqual(['c1', 'c2'])
    expect(view.childrenOf.get('c1')).toEqual([])
    expect(view.childrenOf.get('x')).toEqual([])
    expect(view.edges.map((item) => `${item.prerequisite_id}>${item.mission_id}`)).toEqual([
      'x>c1',
      'x>c2',
      'c1>c2',
    ])
  })

  it('folds a collapsed subtree onto the parent and drops internal edges', () => {
    const nodes = [node('p'), node('c1'), node('c2'), node('x')]
    const edges = [
      edge('1', 'x', 'c1'),
      edge('2', 'x', 'c2'),
      edge('3', 'c1', 'c2'),
    ]
    const view = groupByParent(nodes, edges, parentEdges, new Set(['p']))

    expect(view.nodes.map((item) => item.id)).toEqual(['p', 'x'])
    expect([...view.hidden].sort()).toEqual(['c1', 'c2'])
    // x -> c1 and x -> c2 collapse into one edge to the parent; c1 -> c2 is internal.
    expect(view.edges.map((item) => `${item.prerequisite_id}>${item.mission_id}`)).toEqual([
      'x>p',
    ])
    // The count still describes the merged subtree.
    expect(view.descendantCount.get('p')).toBe(2)
    expect(view.collapsed.has('p')).toBe(true)
    // Hidden children no longer take part in the layout structure.
    expect(view.childrenOf.get('p')).toEqual([])
  })

  it('only marks a merged dependency satisfied when all folded ones are', () => {
    const nodes = [node('p'), node('c1'), node('c2'), node('x')]
    const both = groupByParent(
      nodes,
      [
        edge('1', 'x', 'c1', { is_satisfied: true }),
        edge('2', 'x', 'c2', { is_satisfied: true }),
      ],
      parentEdges,
      new Set(['p']),
    )
    expect(both.edges).toHaveLength(1)
    expect(both.edges[0]).toMatchObject({
      prerequisite_id: 'x',
      mission_id: 'p',
      is_satisfied: true,
    })

    const partial = groupByParent(
      nodes,
      [
        edge('1', 'x', 'c1', { is_satisfied: true }),
        edge('2', 'x', 'c2', { is_satisfied: false }),
      ],
      parentEdges,
      new Set(['p']),
    )
    expect(partial.edges[0].is_satisfied).toBe(false)
  })

  it('recomputes cross-milestone for the visible endpoints', () => {
    const nodes = [
      node('p', { milestone_id: 'm1' }),
      node('c1', { milestone_id: 'm2' }),
      node('x', { milestone_id: 'm2' }),
    ]
    const view = groupByParent(
      nodes,
      [edge('1', 'x', 'c1')],
      [{ parent_id: 'p', child_id: 'c1' }],
      new Set(['p']),
    )
    // x (m2) -> p (m1): still cross-milestone after the merge.
    expect(view.edges[0]).toMatchObject({ prerequisite_id: 'x', mission_id: 'p' })
    expect(view.edges[0].cross_milestone).toBe(true)
  })

  it('reveals the ancestors of a hidden node', () => {
    const nodes = [node('p'), node('c1'), node('c2')]
    expect([...revealPath(nodes, parentEdges, new Set(['p']), 'c2')]).toEqual([])
    expect([
      ...revealPath(nodes, parentEdges, new Set(['p']), 'p'),
    ]).toEqual(['p'])
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

  it('emits toggleCollapse when a parent card folds its subtasks', async () => {
    const grouping = {
      descendantCount: new Map([['p', 1]]),
      collapsed: new Set<string>(),
      depth: new Map([
        ['p', 0],
        ['c', 1],
      ]),
      childrenOf: new Map([['p', ['c']]]),
    }
    const wrapper = mount(DependencyGraph, {
      props: { nodes: [node('p'), node('c')], edges: [], grouping },
    })
    const toggle = wrapper.find('.ws-card__toggle')
    expect(toggle.exists()).toBe(true)
    await toggle.trigger('click')
    expect(wrapper.emitted('toggleCollapse')?.[0]).toEqual(['p'])
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
