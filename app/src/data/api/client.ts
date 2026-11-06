// HTTP client of the API (CONTRACT.md §5). `/api` goes through Vite's proxy to :8000, mock or real.

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>

/** Empty filters are left out of the URL, so `?entity=` never means «the entity with an empty name». */
export function buildUrl(path: string, params: QueryParams = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== '') search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

/** A document path keeps its slashes: only each segment is encoded. */
export const encodePath = (path: string) => path.split('/').map(encodeURIComponent).join('/')

async function toError(res: Response): Promise<ApiError> {
  let message = `Error ${res.status}`
  try {
    const problem = (await res.json()) as { title?: string; detail?: unknown }
    if (typeof problem.detail === 'string') message = problem.detail
    else if (problem.title) message = problem.title
  } catch {
    /* the body is not problem+json: the status is all there is */
  }
  return new ApiError(res.status, message)
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw await toError(res)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const get = <T>(path: string, params?: QueryParams, signal?: AbortSignal) => request<T>(buildUrl(path, params), { signal })

const withBody = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const post = <T>(path: string, body?: unknown) => request<T>(path, withBody('POST', body))
export const put = <T>(path: string, body: unknown) => request<T>(path, withBody('PUT', body))
export const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })
export const postFile = <T>(path: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request<T>(path, { method: 'POST', body: form })
}
