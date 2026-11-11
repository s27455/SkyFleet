import { useCallback, useEffect, useState } from 'react'

export type ResourceState<T> =
  { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error' }

/**
 * Loads a backend resource once, with a retry for failed requests and no fallback data.
 * `load` must be a stable reference (a module-level function), not an inline closure.
 */
export function useApiResource<T>(load: (signal: AbortSignal) => Promise<T>): {
  state: ResourceState<T>
  retry: () => void
} {
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: 'ready', data })
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setState({ status: 'error' })
      })

    return () => controller.abort()
  }, [load, attempt])

  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  return { state, retry }
}
