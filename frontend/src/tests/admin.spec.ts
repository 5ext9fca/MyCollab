import { afterEach, describe, expect, it, vi } from 'vitest'

import { approveRegistration, listRegistrations, rejectRegistration } from '../api/admin'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const emptyPage = { count: 0, next: null, previous: null, results: [] }

describe('admin api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists registrations with a status filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(emptyPage))
    vi.stubGlobal('fetch', fetchMock)

    await listRegistrations({ status: 'Pending' })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/registrations/?status=Pending')
  })

  it('posts to the approve endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'r1', status: 'Approved' }))
    vi.stubGlobal('fetch', fetchMock)

    await approveRegistration('r1')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/registrations/r1/approve/')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it('sends the rejection note', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'r1', status: 'Rejected' }))
    vi.stubGlobal('fetch', fetchMock)

    await rejectRegistration('r1', '资料不完整')

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.body).toBe(JSON.stringify({ note: '资料不完整' }))
  })
})
