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
