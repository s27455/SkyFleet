import { useCallback, useEffect, useState } from 'react'

import { getHubs } from '../../api/hubs'
import type { Hub } from '../../types/hub'

export type HubsState =
  { status: 'loading' } | { status: 'ready'; hubs: readonly Hub[] } | { status: 'error' }

/** Loads Hubs from the backend once, with a retry for failed requests. No mock fallback. */
export function useHubs(): { state: HubsState; retry: () => void } {
  const [state, setState] = useState<HubsState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    getHubs(controller.signal)
      .then((hubs) => {
        if (!controller.signal.aborted) setState({ status: 'ready', hubs })
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setState({ status: 'error' })
      })

    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  return { state, retry }
}
