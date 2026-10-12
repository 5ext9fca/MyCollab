import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildQuery, listMissions } from '../api/missions'

describe('buildQuery', () => {
  it('omits empty values and stringifies the rest', () => {
    expect(buildQuery({ status: 'Open', search: '', tag: undefined, page: 1 })).toBe(
      '?status=Open&page=1',
    )
  })

  it('repeats array params for multi-value filters', () => {
    expect(buildQuery({ tag: ['Unity', 'Gameplay'], page: 1 })).toBe(
      '?tag=Unity&tag=Gameplay&page=1',
    )
  })

  it('skips empty entries inside array params', () => {
    expect(buildQuery({ tag: ['Unity', ''], search: 'x' })).toBe('?tag=Unity&search=x')
  })
})

describe('listMissions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requests the expected URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listMissions({ status: 'Open', page: 2 })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/missions/?status=Open&page=2')
  })
})
