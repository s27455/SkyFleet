import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

/** True when the user asked the system for less motion; flights then jump between snapshots. */
export function usePrefersReducedMotion(): boolean {
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  const [reduced, setReduced] = useState(() => supported && window.matchMedia(QUERY).matches)

  useEffect(() => {
    if (!supported) return
    const query = window.matchMedia(QUERY)
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [supported])

  return reduced
}
