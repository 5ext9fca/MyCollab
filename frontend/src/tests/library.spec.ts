import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteLibraryFile,
  formatFileSize,
  libraryMarkdown,
  listLibraryFiles,
  uploadLibraryFile,
} from '../api/library'
import type { LibraryFile } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const image: LibraryFile = {
  id: 'f1',
  original_name: 'shot.png',
  content_type: 'image/png',
  size: 2048,
  url: '/api/library/files/f1/',
  created_at: '2026-01-01T00:00:00Z',
}

describe('library api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists own files with paging params', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ count: 0, next: null, previous: null, results: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await listLibraryFiles({ page: 2, page_size: 20 })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/library/files/?page=2&page_size=20')
  })

  it('uploads multipart without a JSON content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(image, 201))
    vi.stubGlobal('fetch', fetchMock)

    const file = new File([new Uint8Array([1, 2, 3])], 'shot.png', { type: 'image/png' })
    await uploadLibraryFile(file)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/library/files/')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('deletes a file', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteLibraryFile('f1')).resolves.toBeUndefined()

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/library/files/f1/')
    expect(init.method).toBe('DELETE')
  })

  it('builds image and link markdown for library files', () => {
    expect(libraryMarkdown(image)).toBe('![shot.png](/api/library/files/f1/)')
    expect(
      libraryMarkdown({
        ...image,
        content_type: 'application/pdf',
        original_name: 'spec.pdf',
      }),
    ).toBe('[spec.pdf](/api/library/files/f1/)')
  })

  it('formats file sizes', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2.0 KB')
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
