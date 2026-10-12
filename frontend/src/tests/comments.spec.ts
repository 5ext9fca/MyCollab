import { afterEach, describe, expect, it, vi } from 'vitest'

import { createComment, deleteComment, listComments, updateComment } from '../api/comments'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('comments api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists comments for a mission with paging params', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ count: 0, next: null, previous: null, results: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await listComments('m1', { page: 2, page_size: 20 })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/missions/m1/comments/?page=2&page_size=20')
  })

  it('posts new comment content', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'c1', content: 'hi' }, 201))
    vi.stubGlobal('fetch', fetchMock)

    await createComment('m1', 'hi')

    const call = fetchMock.mock.calls[0]
    expect(call[0]).toBe('/api/missions/m1/comments/')
    expect((call[1] as RequestInit).method).toBe('POST')
    expect((call[1] as RequestInit).body).toBe(JSON.stringify({ content: 'hi' }))
  })

  it('patches an existing comment', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'c1', content: 'new' }))
    vi.stubGlobal('fetch', fetchMock)

    await updateComment('c1', 'new')

    const call = fetchMock.mock.calls[0]
    expect(call[0]).toBe('/api/comments/c1/')
    expect((call[1] as RequestInit).method).toBe('PATCH')
  })

  it('deletes a comment', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteComment('c1')).resolves.toBeUndefined()

    const call = fetchMock.mock.calls[0]
    expect(call[0]).toBe('/api/comments/c1/')
    expect((call[1] as RequestInit).method).toBe('DELETE')
  })
})
