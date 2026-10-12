/** Per-user file library.
 *
 * Uploads land in the caller's library; Markdown may only reference the
 * author's own files (via ``url``) or an external URL.
 */
import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type { LibraryFile, Paginated } from './types'

export const listLibraryFiles = (params: QueryParams = {}): Promise<Paginated<LibraryFile>> =>
  request<Paginated<LibraryFile>>('GET', `/api/library/files/${buildQuery(params)}`)

export const uploadLibraryFile = (file: File): Promise<LibraryFile> => {
  const body = new FormData()
  body.append('file', file)
  return request<LibraryFile>('POST', '/api/library/files/', body)
}

export const deleteLibraryFile = (id: string): Promise<void> =>
  request<void>('DELETE', `/api/library/files/${id}/`)

/** Markdown snippet referencing a library file (image or plain link). */
export function libraryMarkdown(file: LibraryFile): string {
  const label = file.original_name.replace(/[[\]]/g, '')
  return file.content_type.startsWith('image/')
    ? `![${label}](${file.url})`
    : `[${label}](${file.url})`
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
