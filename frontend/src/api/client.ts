/** Typed fetch wrapper: JSON, session cookies, CSRF, and the
 * ``{code, message, field_errors}`` error envelope used by the API. */

export interface ApiErrorBody {
  code: string
  message: string
  field_errors: Record<string, string[]>
}

export type QueryParamValue =
  | string
  | number
  | boolean
  | undefined
  | null
  | ReadonlyArray<string | number>

export type QueryParams = Record<string, QueryParamValue>

/** Serialize defined, non-empty params into a ``?a=1&b=2`` query string.
 * Array values become repeated params (``?tag=a&tag=b``), which the API
 * reads with ``getlist`` for multi-value filters. */
export function buildQuery(params: QueryParams): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== null && item !== '') {
          search.append(key, String(item))
        }
      }
    } else {
      search.set(key, String(value))
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

export class ApiException extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors: Record<string, string[]>

  constructor(
    status: number,
    code: string,
    message: string,
    fieldErrors: Record<string, string[]> = {},
  ) {
    super(message)
    this.name = 'ApiException'
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[2]) : null
}

/** Fetch the CSRF cookie. Call once before the first unsafe request (login). */
export async function ensureCsrf(): Promise<void> {
  await fetch('/api/auth/csrf/', { method: 'GET', credentials: 'same-origin' })
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const init: RequestInit = { method, headers, credentials: 'same-origin' }

  if (body instanceof FormData) {
    // Let the browser set the multipart boundary; do not set Content-Type.
    init.body = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
    const token = getCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }

  const response = await fetch(path, init)
  if (response.status === 204) return undefined as T

  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }

  if (!response.ok) {
    const error = (data ?? {}) as Partial<ApiErrorBody>
    throw new ApiException(
      response.status,
      error.code ?? 'error',
      error.message ?? `请求失败（${response.status}）`,
      error.field_errors ?? {},
    )
  }
  return data as T
}
