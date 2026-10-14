import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { WorkspaceEdge, WorkspaceNode } from '../api/types'
import DependencyGraph from '../components/DependencyGraph.vue'
import { GROUP_GAP, GROUP_INDENT, NODE_HEIGHT } from '../workspace/dto'

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
    expect(wrapper.findAll('.vue-flow__node')).toHaveLength(3)
    expect(wrapper.text()).toContain('孤立任务')

    wrapper.unmount()
  })

  it('mounts a grouped subtask directly below its parent', async () => {
    const grouping = {
      descendantCount: new Map([['p', 1]]),
      collapsed: new Set<string>(),
      depth: new Map([
        ['p', 0],
        ['c', 1],
      ]),
      groups: [{ id: 'p', memberIds: ['p', 'c'], depths: [0, 1] }],
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
    const wrappers = wrapper.findAll('.vue-flow__node')
    const parent = wrappers.find((element) => element.text().includes('AAA'))
    const child = wrappers.find((element) => element.text().includes('BBB'))
    expect(parent).toBeTruthy()
    expect(child).toBeTruthy()

    const p = parse(parent!.attributes('style') ?? '')
    const c = parse(child!.attributes('style') ?? '')
    expect(p).toBeTruthy()
    expect(c).toBeTruthy()
    expect(c!.y - p!.y).toBe(NODE_HEIGHT + GROUP_GAP)
    expect(c!.x - p!.x).toBe(GROUP_INDENT)

    wrapper.unmount()
  })
})
