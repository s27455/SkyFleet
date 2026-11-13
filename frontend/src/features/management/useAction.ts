import { useCallback, useRef, useState } from 'react'

import { describeApiError } from '../../api/client'

/**
 * Runs one backend write at a time. A second call while one is in flight is ignored (no duplicate
 * submissions), and a failure is kept as readable text instead of being thrown into the UI.
 * `run` resolves to true only when the action succeeded.
 */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const running = useRef(false)

  const run = useCallback(async (action: () => Promise<unknown>) => {
    if (running.current) return false
    running.current = true
    setBusy(true)
    setError(null)
    try {
      await action()
      return true
    } catch (caught) {
      setError(describeApiError(caught))
      return false
    } finally {
      running.current = false
      setBusy(false)
    }
  }, [])

  const clearError = useCallback(() => setError(null), [])

  return { busy, error, run, clearError }
}
