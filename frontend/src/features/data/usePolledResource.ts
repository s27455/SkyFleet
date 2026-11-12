import { useCallback, useEffect, useRef, useState } from 'react'

import { REQUEST_TIMEOUT_MS } from './polling'
import type { ResourceState } from './useApiResource'

export interface PolledResource<T> {
  /** loading until the first answer; ready with the latest good data; error if there never was one. */
  state: ResourceState<T>
  /** True when the latest refresh failed but older data is still shown (never blanked). */
  stale: boolean
  /** `performance.now()` of the last answer; only tracked with `trackReceivedAt`, else null. */
  receivedAt: number | null
  /** Starts over with a loading state (the Retry button). */
  retry: () => void
  /**
   * Reads again as soon as possible without a loading state (after an action such as a mission
   * start). If a read is already running, one more read follows right after it, so the answer
   * always reflects the moment of the call.
   */
  refresh: () => void
}

export interface PolledResourceOptions {
  /**
   * Re-render on every answer and expose when it arrived, for interpolating between polls. Off by
   * default: consumers that only need the data are not re-rendered when it did not change.
   */
  trackReceivedAt?: boolean
}

/** Structural sharing: unchanged data keeps its identity, so consumers do not rebuild needlessly. */
const sameData = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/**
 * Reads a backend resource repeatedly: the next request starts `intervalMs` after the previous one
 * finished (never overlapping), polling pauses while the tab is hidden, requests are aborted on
 * unmount, a request that takes too long counts as a failure, and a failed refresh keeps the last
 * good data and flags it `stale` instead of blanking it. `intervalMs = null` reads once (plus
 * retry/refresh). `load` must be a stable reference.
 */
export function usePolledResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  intervalMs: number | null,
  options: PolledResourceOptions = {},
): PolledResource<T> {
  const trackReceivedAt = options.trackReceivedAt ?? false
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading' })
  const [stale, setStale] = useState(false)
  const [receivedAt, setReceivedAt] = useState<number | null>(null)
  const [attempt, setAttempt] = useState(0)
  const refreshRef = useRef<() => void>(() => {})

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let running = false
    let queued = false

    const schedule = () => {
      if (intervalMs === null || controller.signal.aborted) return
      timer = setTimeout(tick, intervalMs)
    }

    const tick = () => {
      if (running || controller.signal.aborted) return
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule() // keep checking; nothing is requested while hidden
        return
      }
      running = true

      // One controller per request, so a timeout cancels just that request.
      const request = new AbortController()
      const abortRequest = () => request.abort()
      controller.signal.addEventListener('abort', abortRequest)
      let timeout: ReturnType<typeof setTimeout> | undefined
      const timedOut = new Promise<never>((_, reject) => {
        timeout = setTimeout(() => {
          request.abort()
          reject(new Error('The request took too long'))
        }, REQUEST_TIMEOUT_MS.value)
      })

      Promise.race([load(request.signal), timedOut])
        .then((data) => {
          if (controller.signal.aborted) return
          if (trackReceivedAt) setReceivedAt(performance.now())
          setStale(false)
          setState((previous) =>
            previous.status === 'ready' && sameData(previous.data, data)
              ? previous
              : { status: 'ready', data },
          )
        })
        .catch(() => {
          if (controller.signal.aborted) return
          // Keep showing the last good data; only a failed first read is an error.
          setState((previous) => (previous.status === 'ready' ? previous : { status: 'error' }))
          setStale(true)
        })
        .finally(() => {
          clearTimeout(timeout)
          controller.signal.removeEventListener('abort', abortRequest)
          running = false
          if (queued && !controller.signal.aborted) {
            queued = false
            tick() // a refresh was requested while this read ran: read again now
          } else {
            schedule()
          }
        })
    }

    const onVisibility = () => {
      if (document.visibilityState === 'visible' && intervalMs !== null) {
        clearTimeout(timer)
        tick()
      }
    }

    refreshRef.current = () => {
      if (running) {
        queued = true
        return
      }
      clearTimeout(timer)
      tick()
    }
    document.addEventListener('visibilitychange', onVisibility)
    tick()

    return () => {
      controller.abort()
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [load, intervalMs, attempt, trackReceivedAt])

  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setStale(false)
    setAttempt((current) => current + 1)
  }, [])
  const refresh = useCallback(() => refreshRef.current(), [])

  return { state, stale, receivedAt, retry, refresh }
}
