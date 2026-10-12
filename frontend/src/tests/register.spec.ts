import { afterEach, describe, expect, it, vi } from 'vitest'

import { register } from '../api/auth'

describe('register', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('posts the payload to the public registration endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'r1', status: 'Pending' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await register({ username: 'newbie', password: 'Str0ngPass!23', email: 'n@example.com' })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/register/')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      username: 'newbie',
      password: 'Str0ngPass!23',
      email: 'n@example.com',
    })
  })
})
