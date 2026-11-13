const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number | undefined
  /** The backend's `detail` for an error response, when it sent a JSON body (untrusted). */
  readonly detail: unknown

  constructor(message: string, status?: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError'

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch (error) {
    if (isAbort(error)) throw error
    throw new ApiError('Backend is unreachable')
  }

  if (!response.ok) {
    let detail: unknown
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(`Request failed with status ${response.status}`, response.status, detail)
  }
  // 204 No Content (a successful DELETE) has no body to parse.
  if (response.status === 204) return undefined as T
  try {
    return (await response.json()) as T
  } catch (error) {
    if (isAbort(error)) throw error
    throw new ApiError('Backend returned a response that is not valid JSON', response.status)
  }
}

/** Shared GET helper. All backend HTTP calls go through this module. */
export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal })
}

/** Shared POST helper for backend actions that take no body. */
export function apiPost<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'POST', signal })
}

/** JSON-body helper for administrative writes (POST create, PATCH update). */
export function apiSend<T>(
  method: 'POST' | 'PATCH',
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

/** DELETE helper; resolves with nothing on 204. */
export function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  return request<void>(path, { method: 'DELETE', signal })
}

type ValidationItem = { loc?: unknown; msg?: unknown }

/**
 * Turns a failed write into text for the operator. The backend sends `{code, message}` for
 * business rejections (404/409) and FastAPI's list of `{loc, msg}` for validation errors (422);
 * anything else gets a generic message. The detail is untrusted, so it is only ever shown as text.
 */
export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong. Please try again.'
  const { detail, status } = error
  if (status === undefined) return error.message
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = (detail as ValidationItem[])
      .map((item) => {
        if (typeof item?.msg !== 'string') return null
        const field = Array.isArray(item.loc) ? String(item.loc[item.loc.length - 1] ?? '') : ''
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .filter((part): part is string => part !== null)
    if (parts.length > 0) return parts.join('; ')
  }
  if (typeof detail === 'object' && detail !== null) {
    const { message } = detail as { message?: unknown }
    if (typeof message === 'string') return message
  }
  return `The backend rejected the request (status ${status}).`
}
