import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  addDependency,
  buildQuery,
  claimMission,
  listMissions,
  removeDependency,
  reviewMission,
  submitMission,
} from '../api/missions'

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

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

  it('serializes the extended mission filters', () => {
    expect(
      buildQuery({
        type: 'Bug',
        priority: 'P0',
        milestone: 'm-1',
        blocked: 'true',
        ordering: 'priority',
      }),
    ).toBe('?type=Bug&priority=P0&milestone=m-1&blocked=true&ordering=priority')
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

describe('mission write actions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('claimMission posts the expected version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'm1' }))
    vi.stubGlobal('fetch', fetchMock)

    await claimMission('m1', 7)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/missions/m1/claim/')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ expected_version: 7 })
  })

  it('submitMission sends the evidence payload plus the version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'm1' }))
    vi.stubGlobal('fetch', fetchMock)

    await submitMission(
      'm1',
      {
        description: 'done',
        verification_description: 'manual',
        build_references: [
          { provider: 'CI', build_id: '42', platform: 'Windows', status: 'Succeeded' },
        ],
      },
      3,
    )

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      description: 'done',
      verification_description: 'manual',
      build_references: [
        { provider: 'CI', build_id: '42', platform: 'Windows', status: 'Succeeded' },
      ],
      expected_version: 3,
    })
  })

  it('reviewMission posts the new decision shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'm1' }))
    vi.stubGlobal('fetch', fetchMock)

    await reviewMission(
      'm1',
      {
        submission_id: 's1',
        decision: 'accept',
        comment: 'verified',
        verified_build_reference_id: 'b1',
      },
      4,
    )

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      submission_id: 's1',
      decision: 'accept',
      comment: 'verified',
      verified_build_reference_id: 'b1',
      expected_version: 4,
    })
  })

  it('addDependency posts the prerequisite and version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'm1' }))
    vi.stubGlobal('fetch', fetchMock)

    await addDependency('m1', 'p1', 2)

    expect(fetchMock.mock.calls[0][0]).toBe('/api/missions/m1/dependencies/')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      prerequisite_id: 'p1',
      expected_version: 2,
    })
  })

  it('removeDependency puts the version in the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await removeDependency('m1', 'd1', 5)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/missions/m1/dependencies/d1/?expected_version=5')
    expect(init.method).toBe('DELETE')
  })
})
