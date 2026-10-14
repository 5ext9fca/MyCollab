import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getWorkspaceGraph, getWorkspaceOverview } from '../api/workspace'
import type { WorkspaceEdge, WorkspaceGroup, WorkspaceNode } from '../api/types'
import DependencyGraph from '../components/DependencyGraph.vue'
import WorkspaceMilestoneBoard from '../components/WorkspaceMilestoneBoard.vue'
import { assignLayers, directRelations, layoutGraph } from '../workspaceLayout'

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

const edge = (id: string, prerequisite: string, mission: string): WorkspaceEdge => ({
  id,
  prerequisite_id: prerequisite,
  mission_id: mission,
  is_satisfied: false,
  cross_milestone: false,
})

const stubs = {
  'el-tag': { template: '<span><slot /></span>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-empty': { template: '<div />' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<div><slot /></div>' },
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

describe('workspace layout', () => {
  it('assigns dependency layers from prerequisite to dependent', () => {
    const nodes = [node('a'), node('b'), node('c'), node('d'), node('e')]
    const edges = [edge('1', 'a', 'c'), edge('2', 'b', 'c'), edge('3', 'c', 'd')]
    const layers = assignLayers(nodes, edges)
    expect(layers.get('a')).toBe(0)
    expect(layers.get('b')).toBe(0)
    expect(layers.get('c')).toBe(1)
    expect(layers.get('d')).toBe(2)
    expect(layers.get('e')).toBe(0)
  })

  it('keeps isolated nodes visible and builds edge paths', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges = [edge('1', 'a', 'b')]
    const layout = layoutGraph(nodes, edges)
    expect(layout.nodes).toHaveLength(3)
    const c = layout.positions.get('c')
    expect(c).toBeTruthy()
    expect(layout.dependencyEdges[0].path).toMatch(/^M /)
    expect(layout.width).toBeGreaterThan(0)
    expect(layout.height).toBeGreaterThan(0)
  })

  it('reports direct prerequisites and dependents', () => {
    const edges = [edge('1', 'a', 'c'), edge('2', 'b', 'c'), edge('3', 'c', 'd')]
    const relations = directRelations('c', edges)
    expect([...relations.prerequisites].sort()).toEqual(['a', 'b'])
    expect([...relations.dependents]).toEqual(['d'])
  })
})

function groupFixture(): WorkspaceGroup {
  return {
    milestone: { id: 'm2', name: '首个可玩版本', status: 'Active', due_date: '2026-12-01' },
    is_unassigned: false,
    full_counts: { total: 3, effective_total: 2, done: 1, progress: 0.5 },
    matched_counts: { Open: 2, InProgress: 0, Submitted: 0, Done: 0, Cancelled: 0 },
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

describe('DependencyGraph', () => {
  it('renders every node, including isolated ones, and moves a node on click', async () => {
    const wrapper = mount(DependencyGraph, {
      props: {
        nodes: [node('a'), node('b'), node('e', { title: '孤立任务' })],
        edges: [edge('1', 'a', 'b')],
      },
      global: { stubs },
    })
    expect(wrapper.findAll('.graph__node')).toHaveLength(3)
    expect(wrapper.text()).toContain('孤立任务')
    expect(wrapper.find('.graph-edge').exists()).toBe(true)

    await wrapper.findAll('.ws-card')[0].trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['a'])
  })
})

describe('WorkspaceMilestoneBoard', () => {
  it('renders milestone totals, matched counts and a load-more hint', () => {
    const wrapper = mount(WorkspaceMilestoneBoard, {
      props: {
        groups: [groupFixture()],
        columns: ['Open', 'InProgress', 'Submitted', 'Done', 'Cancelled'],
        columnLabels: {
          Open: '待认领',
          InProgress: '进行中',
          Submitted: '待验收',
          Done: '已完成',
          Cancelled: '已取消',
        },
        filtersActive: true,
        selectedId: null,
      },
      global: { stubs },
    })
    const text = wrapper.text()
    expect(text).toContain('首个可玩版本')
    expect(text).toContain('里程碑总计 1 / 2')
    expect(text).toContain('动画接入')
    expect(text).toContain('已显示 1 / 2')
  })

  it('emits loadMore when a column is truncated', async () => {
    const wrapper = mount(WorkspaceMilestoneBoard, {
      props: {
        groups: [groupFixture()],
        columns: ['Open', 'InProgress', 'Submitted', 'Done', 'Cancelled'],
        columnLabels: {
          Open: '待认领',
          InProgress: '进行中',
          Submitted: '待验收',
          Done: '已完成',
          Cancelled: '已取消',
        },
        filtersActive: true,
        selectedId: null,
      },
      global: { stubs },
    })
    const button = wrapper
      .findAll('button')
      .find((item) => item.text().includes('加载更多'))
    expect(button).toBeTruthy()
    await button!.trigger('click')
    expect(wrapper.emitted('loadMore')).toBeTruthy()
  })
})
