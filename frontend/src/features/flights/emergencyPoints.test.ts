import { describe, expect, it } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Flight } from '../../types/flight'
import { droneEmergencies, emergencyPoints, interruptedOrderIds } from './emergencyPoints'
import { isFailable } from './flightStatus'

const flight = (overrides: Partial<Flight> = {}): Flight => ({
  missionId: 'MIS-1',
  orderId: 'ORD-1',
  droneId: 'DRN-1',
  missionStatus: 'IN_FLIGHT',
  phase: 'OUTBOUND',
  progress: 0.3,
  position: [18.6, 54.38],
  batteryPct: 90,
  target: { position: [18.61, 54.39], etaS: 6 },
  originHubId: 'hub-a',
  plannedReturnHubId: 'hub-a',
  landingTargetHubId: 'hub-a',
  startedAt: '2026-11-13T10:00:00Z',
  deliveredAt: null,
  recalledAt: null,
  failedAt: null,
  updatedAt: '2026-11-13T10:00:08Z',
  snapshotAgeS: 1,
  emergency: null,
  ...overrides,
})

const drone = (status: Drone['status']): Drone =>
  ({ id: 'DRN-1', status, coordinates: [18.6, 54.38] }) as Drone

describe('emergencyPoints', () => {
  it('has no point for a flight the backend did not mark as failed', () => {
    expect(emergencyPoints([flight()], [drone('IN_FLIGHT')])).toEqual([])
  })

  it('marks the target of a failing flight as an approach', () => {
    const points = emergencyPoints(
      [flight({ failedAt: '2026-11-13T10:00:08Z', phase: 'EMERGENCY_APPROACH' })],
      [drone('IN_FLIGHT')],
    )

    expect(points).toEqual([
      { droneId: 'DRN-1', orderId: 'ORD-1', level: 'approach', position: [18.61, 54.39] },
    ])
  })

  it('marks the landing place while the drone is grounded, and clears it once it is not', () => {
    const grounded = flight({
      failedAt: '2026-11-13T10:00:08Z',
      phase: 'EMERGENCY',
      target: null,
      position: [18.605, 54.385],
      emergency: {
        reason: 'DRONE_FAILURE',
        at: '2026-11-13T10:00:15Z',
        position: [18.605, 54.385],
      },
    })

    expect(emergencyPoints([grounded], [drone('MAINTENANCE')])).toEqual([
      { droneId: 'DRN-1', orderId: 'ORD-1', level: 'grounded', position: [18.605, 54.385] },
    ])
    expect(emergencyPoints([grounded], [drone('IDLE')])).toEqual([])
  })

  it('does not treat an ordinary emergency (no failure) as a drone failure', () => {
    const ordinary = flight({ phase: 'EMERGENCY', emergency: null })

    expect(emergencyPoints([ordinary], [drone('MAINTENANCE')])).toEqual([])
  })
})

describe('droneEmergencies and interruptedOrderIds', () => {
  it('maps drones to their level', () => {
    const levels = droneEmergencies([
      { droneId: 'DRN-1', orderId: 'ORD-1', level: 'approach', position: [18.6, 54.4] },
    ])

    expect(levels.get('DRN-1')).toBe('approach')
  })

  it('flags only undelivered orders of failed flights as interrupted', () => {
    const ids = interruptedOrderIds([
      flight({ orderId: 'ORD-A', failedAt: '2026-11-13T10:00:08Z' }),
      flight({
        orderId: 'ORD-B',
        failedAt: '2026-11-13T10:00:08Z',
        deliveredAt: '2026-11-13T10:00:05Z',
      }),
      flight({ orderId: 'ORD-C' }),
    ])

    expect([...ids]).toEqual(['ORD-A'])
  })
})

describe('isFailable', () => {
  it('is true for a flying, not yet failed flight', () => {
    expect(isFailable(flight())).toBe(true)
    expect(isFailable(flight({ phase: 'RETURNING', recalledAt: '2026-11-13T10:00:05Z' }))).toBe(
      true,
    )
  })

  it('is false once failed, grounded, landed or not in flight', () => {
    expect(isFailable(flight({ failedAt: '2026-11-13T10:00:08Z' }))).toBe(false)
    expect(isFailable(flight({ phase: 'EMERGENCY_APPROACH' }))).toBe(false)
    expect(isFailable(flight({ phase: 'EMERGENCY' }))).toBe(false)
    expect(isFailable(flight({ phase: 'LANDED' }))).toBe(false)
    expect(isFailable(flight({ missionStatus: 'COMPLETED' }))).toBe(false)
  })
})
