import { afterEach, describe, expect, it, vi } from 'vitest'

import { request } from '../api/client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('request', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })

  it('adds the CSRF header and credentials on unsafe requests', async () => {
    document.cookie = 'csrftoken=abc123'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await request<{ ok: boolean }>('POST', '/api/missions/', { title: 'x' })

    expect(result).toEqual({ ok: true })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>)['X-CSRFToken']).toBe('abc123')
    expect(init.credentials).toBe('same-origin')
  })

  it('parses the error envelope into ApiException', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ code: 'claim_conflict', message: '已被认领', field_errors: {} }, 409),
      ),
    )

    await expect(request('POST', '/api/missions/1/claim/', {})).rejects.toMatchObject({
      status: 409,
      code: 'claim_conflict',
      message: '已被认领',
    })
  })

  it('returns undefined for 204 responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('POST', '/api/auth/logout/')).resolves.toBeUndefined()
  })
})
