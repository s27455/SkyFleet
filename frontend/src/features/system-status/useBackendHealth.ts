import { useEffect, useState } from 'react'

import { getHealth } from '../../api/health'

export type BackendHealth = 'checking' | 'connected' | 'unreachable'

const POLL_INTERVAL_MS = 10_000

/** Polls the backend health endpoint so the UI can show connection state. */
export function useBackendHealth(): BackendHealth {
  const [health, setHealth] = useState<BackendHealth>('checking')

  useEffect(() => {
    let controller = new AbortController()

    const check = async () => {
      controller.abort()
      controller = new AbortController()
      try {
        await getHealth(controller.signal)
        setHealth('connected')
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setHealth('unreachable')
      }
    }

    void check()
    const intervalId = window.setInterval(() => void check(), POLL_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
      controller.abort()
    }
  }, [])

  return health
}
