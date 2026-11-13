import { describe, expect, it } from 'vitest'

import type { Flight } from '../../types/flight'
import { canAnimateFlights, flightsByDrone, isActiveFlight } from './flightStatus'

const flight = (overrides: Partial<Flight> = {}): Flight => ({
  missionId: 'MIS-1',
  orderId: 'ORD-1',
  droneId: 'DRN-1',
  missionStatus: 'IN_FLIGHT',
  phase: 'OUTBOUND',
  progress: 0.1,
  position: [18.6, 54.4],
  batteryPct: 90,
  target: null,
  originHubId: 'hub-a',
  plannedReturnHubId: 'hub-a',
  landingTargetHubId: 'hub-a',
  startedAt: '2026-11-12T10:00:00Z',
  deliveredAt: null,
  recalledAt: null,
  failedAt: null,
  updatedAt: '2026-11-12T10:00:01Z',
  snapshotAgeS: 0,
  emergency: null,
  ...overrides,
})

describe('canAnimateFlights', () => {
  it('allows the glide only when nothing says the data is old or motion unwanted', () => {
    expect(
      canAnimateFlights({ reducedMotion: false, workerStale: false, refreshFailed: false }),
    ).toBe(true)
    expect(
      canAnimateFlights({ reducedMotion: true, workerStale: false, refreshFailed: false }),
    ).toBe(false)
    expect(
      canAnimateFlights({ reducedMotion: false, workerStale: true, refreshFailed: false }),
    ).toBe(false)
    expect(
      canAnimateFlights({ reducedMotion: false, workerStale: false, refreshFailed: true }),
    ).toBe(
      false, // the notice says drones stay at their last known positions, so they must
    )
  })
})

describe('isActiveFlight', () => {
  it.each(['OUTBOUND', 'DELIVERING', 'RETURNING', 'DIVERTING'] as const)(
    '%s is moving',
    (phase) => {
      expect(isActiveFlight(flight({ phase }))).toBe(true)
    },
  )

  it.each(['LANDED', 'EMERGENCY'] as const)('%s is not moving', (phase) => {
    expect(isActiveFlight(flight({ phase }))).toBe(false)
  })
})

describe('flightsByDrone', () => {
  it('keeps one flight per drone', () => {
    const map = flightsByDrone([
      flight({ droneId: 'DRN-1' }),
      flight({ missionId: 'MIS-2', droneId: 'DRN-2' }),
    ])

    expect([...map.keys()]).toEqual(['DRN-1', 'DRN-2'])
  })

  it('prefers an active flight over an older emergency, whatever the order', () => {
    const emergency = flight({ missionId: 'MIS-OLD', phase: 'EMERGENCY' })
    const active = flight({ missionId: 'MIS-NEW', phase: 'OUTBOUND' })

    expect(flightsByDrone([emergency, active]).get('DRN-1')?.missionId).toBe('MIS-NEW')
    expect(flightsByDrone([active, emergency]).get('DRN-1')?.missionId).toBe('MIS-NEW')
  })
})
