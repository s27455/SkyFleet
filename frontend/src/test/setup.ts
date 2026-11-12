import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { POLL_INTERVALS_MS } from '../features/data/polling'

// Live polling is off by default so existing tests read each resource once; tests of polling
// switch it on explicitly.
POLL_INTERVALS_MS.flights = null
POLL_INTERVALS_MS.fleet = null

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
