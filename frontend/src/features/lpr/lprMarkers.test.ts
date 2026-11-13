import { describe, expect, it } from 'vitest'

import type { LprScenario } from '../../types/lpr'
import { createHelicopterMarkerElement, helicopterLabel } from './lprMarkers'

const SCENARIO: LprScenario = {
  id: 'LPR-1',
  startedAt: '2026-11-13T12:00:00Z',
  endsAt: '2026-11-13T12:03:00Z',
  position: [18.5, 54.3925],
  routeStart: [18.46, 54.3925],
  routeEnd: [18.67, 54.3925],
  speedMs: 80,
  radiusM: 500,
  holdMarginM: 250,
}

describe('LPR helicopter marker', () => {
  it('is a labelled image, not a control, and says what it does in words', () => {
    const element = createHelicopterMarkerElement(SCENARIO)

    expect(element.getAttribute('role')).toBe('img')
    expect(element.getAttribute('aria-label')).toBe(helicopterLabel(SCENARIO))
    expect(helicopterLabel(SCENARIO)).toMatch(/safety zone of 500 m radius.*drones in its way wait/)
    expect(element.dataset.markerKind).toBe('lpr-helicopter')
    expect(element.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})
