import { describe, expect, it } from 'vitest'

import type { LprScenario } from '../../types/lpr'
import { helicopterPosition, zoneFeature } from './helicopter'

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

const metres = (a: readonly number[], b: readonly number[]) =>
  Math.hypot((b[0] - a[0]) * Math.cos((a[1] * Math.PI) / 180) * 111_320, (b[1] - a[1]) * 111_320)

describe('helicopterPosition', () => {
  it('is the answered position when nothing has elapsed', () => {
    expect(helicopterPosition(SCENARIO, 0)).toEqual(SCENARIO.position)
  })

  it('moves along the route at the scenario speed', () => {
    const later = helicopterPosition(SCENARIO, 10)

    expect(metres(SCENARIO.position, later)).toBeCloseTo(800, -1) // 10 s at 80 m/s
    expect(later[0]).toBeGreaterThan(SCENARIO.position[0])
    expect(later[1]).toBeCloseTo(54.3925, 6) // still on the route
  })

  it('stops at the end of the route and never moves backwards', () => {
    expect(helicopterPosition(SCENARIO, 10_000)).toEqual(SCENARIO.routeEnd)
    expect(helicopterPosition(SCENARIO, -5)).toEqual(SCENARIO.position)
  })
})

describe('zoneFeature', () => {
  it('is a closed circle of the given radius around the helicopter', () => {
    const feature = zoneFeature([18.5, 54.3925], 500) as unknown as {
      geometry: { type: string; coordinates: number[][][] }
    }
    const ring = feature.geometry.coordinates[0]

    expect(feature.geometry.type).toBe('Polygon')
    expect(ring[0]).toEqual(ring[ring.length - 1]) // closed
    for (const point of ring) expect(metres([18.5, 54.3925], point)).toBeCloseTo(500, 0)
  })
})
