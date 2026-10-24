import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import DependencyGraph from '../components/DependencyGraph.vue'
import { GANTT_ROW_HEIGHT } from '../composables/useGanttLayout'
import { sourceEdgeColor } from '../workspace/edgeColor'

function node(id: string, title: string): WorkspaceNode {
  return {
    id,
    title,
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
  }
}

const edge: WorkspaceEdge = {
  id: '1',
  prerequisite_id: 'a',
  mission_id: 'b',
  is_satisfied: false,
  cross_milestone: true,
}

describe('DependencyGraph (real Vue Flow)', () => {
  it('mounts Vue Flow and places every node on the canvas', async () => {
    const wrapper = mount(DependencyGraph, {
      props: {
        nodes: [node('a', '前置任务'), node('b', '依赖任务'), node('e', '孤立任务')],
        edges: [edge],
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.find('.vue-flow').exists()).toBe(true)
    // Vue Flow renders one wrapper per node, isolated nodes included.
    expect(wrapper.findAll('.vue-flow__node-mission')).toHaveLength(3)
    expect(wrapper.text()).toContain('孤立任务')

    wrapper.unmount()
  })

  it('按日期绘制任务区间并连接双方结束端', async () => {
    const wrapper = mount(DependencyGraph, {
      props: {
        dateFrom: '2026-10-01', dateTo: '2026-10-31',
        nodes: [{ ...node('a', '前置任务AAA'), planned_start_date: '2026-10-01', planned_end_date: '2026-10-03' }, { ...node('b', '依赖任务BBB'), planned_start_date: '2026-10-04', planned_end_date: '2026-10-08' }],
        edges: [
          { id: '1', prerequisite_id: 'a', mission_id: 'b', is_satisfied: false, cross_milestone: false },
        ],
      },
      attachTo: document.body,
    })
    await flushPromises()

    const parse = (style: string) => {
      const match = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/.exec(style)
      return match ? { x: Number(match[1]), y: Number(match[2]) } : null
    }
    const wrappers = wrapper.findAll('.vue-flow__node-mission')
    const prerequisite = wrappers.find((element) => element.text().includes('AAA'))
    const dependent = wrappers.find((element) => element.text().includes('BBB'))
    expect(prerequisite).toBeTruthy()
    expect(dependent).toBeTruthy()

    const a = parse(prerequisite!.attributes('style') ?? '')
    const b = parse(dependent!.attributes('style') ?? '')
    expect(a).toBeTruthy()
    expect(b).toBeTruthy()
    expect(b!.x - a!.x).toBe(3 * 32)
    expect(b!.y - a!.y).toBe(GANTT_ROW_HEIGHT)
    expect(prerequisite!.findAll('.vue-flow__handle-right')).toHaveLength(2)
    expect(dependent!.findAll('.vue-flow__handle-right')).toHaveLength(2)

    wrapper.unmount()
  })

  it('父子任务保留层级与折叠，日期横轴不再承担父子排布', async () => {
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
      props: {
        nodes: [node('p', '家长任务AAA'), node('c', '子任务BBB')],
        edges: [],
        grouping,
      },
      attachTo: document.body,
    })
    await flushPromises()

    const parse = (style: string) => {
      const match = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/.exec(style)
      return match ? { x: Number(match[1]), y: Number(match[2]) } : null
    }
    const wrappers = wrapper.findAll('.vue-flow__node-mission')
    const parent = wrappers.find((element) => element.text().includes('AAA'))
    const child = wrappers.find((element) => element.text().includes('BBB'))
    expect(parent).toBeTruthy()
    expect(child).toBeTruthy()

    const p = parse(parent!.attributes('style') ?? '')
    const c = parse(child!.attributes('style') ?? '')
    expect(p).toBeTruthy()
    expect(c).toBeTruthy()
    expect(c!.y - p!.y).toBe(GANTT_ROW_HEIGHT)
    expect(c!.x).toBe(p!.x)
    expect(child!.text()).toContain('↳')
    expect(parent!.find('.ws-card__toggle').exists()).toBe(true)

    wrapper.unmount()
  })

  it('paints every edge from one source with the same colour', async () => {
    const wrapper = mount(DependencyGraph, {
      props: {
        nodes: [node('a', '前置任务AAA'), node('b', '依赖任务BBB'), node('c', '依赖任务CCC')],
        edges: [
          { id: '1', prerequisite_id: 'a', mission_id: 'b', is_satisfied: true, cross_milestone: false },
          { id: '2', prerequisite_id: 'a', mission_id: 'c', is_satisfied: false, cross_milestone: false },
          { id: '3', prerequisite_id: 'b', mission_id: 'c', is_satisfied: false, cross_milestone: false },
        ],
      },
      attachTo: document.body,
    })
    await flushPromises()

    const strokeOf = (id: string) =>
      (wrapper.find(`[data-id="${id}"] .vue-flow__edge-path`).element as SVGElement).style.stroke
    // jsdom normalises the inline colour to `rgb(...)`.
    const rgb = (hex: string) =>
      `rgb(${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)})`
    // Both lines from `a` share one colour, whether satisfied or pending.
    expect(strokeOf('1')).toBe(strokeOf('2'))
    expect(strokeOf('1')).not.toBe('')
    // A line from another source is painted differently.
    expect(strokeOf('3')).not.toBe(strokeOf('1'))
    expect(strokeOf('1')).toBe(rgb(sourceEdgeColor('a')))

    wrapper.unmount()
  })
})
