import { afterEach, describe, expect, it, vi } from 'vitest'

import { listTeamMembers } from '../api/auth'

describe('members api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the team member list for the reviewer picker', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: 1, username: 'alice', display_name: 'Alice' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const members = await listTeamMembers()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/members/')
    expect(members).toEqual([{ id: 1, username: 'alice', display_name: 'Alice' }])
  })
})
