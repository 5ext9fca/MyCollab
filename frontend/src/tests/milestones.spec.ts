import { afterEach, describe, expect, it, vi } from 'vitest'

import { listMilestones, transitionMilestone, updateMilestone } from '../api/milestones'

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('milestones api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists milestones with the status filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ count: 0, next: null, previous: null, results: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listMilestones({ status: 'Active', page: 1 })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/milestones/?status=Active&page=1')
  })

  it('updateMilestone sends expected_version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'ms1' }))
    vi.stubGlobal('fetch', fetchMock)

    await updateMilestone('ms1', { expected_version: 2, name: 'M1' })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/milestones/ms1/')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      expected_version: 2,
      name: 'M1',
    })
  })

  it('transitionMilestone posts status, reason and version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'ms1' }))
    vi.stubGlobal('fetch', fetchMock)

    await transitionMilestone('ms1', 'Active', 3, '恢复')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/milestones/ms1/transition/')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      status: 'Active',
      reason: '恢复',
      expected_version: 3,
    })
  })
})
