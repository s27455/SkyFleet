import { describe, expect, it } from 'vitest'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { computeDroneOffsets, droneMarkerLabel } from './droneMarkers'

const MODEL = {
  id: 'SF-1',
  name: 'SkyFleet SF-1 Courier',
  maxPayloadKg: 3,
  maxRangeKm: 20,
  recommendedMissionRangeKm: 14,
  cruiseSpeedKmh: 45,
  nominalFlightTimeMin: 32,
  minBatteryReservePct: 20,
}

function drone(id: string, coordinates: [number, number]): Drone {
  return { id, hubId: 'hub-a', status: 'IDLE', batteryPct: 90, coordinates, model: MODEL }
}

const HUB_POINT: [number, number] = [18.6, 54.4]
const HUB: Hub = {
  id: 'hub-a',
  name: 'Hub A',
  address: 'Ulica 1',
  coordinates: HUB_POINT,
  droneCapacity: 50,
}

const distance = ([x, y]: readonly [number, number]) => Math.hypot(x, y)

describe('computeDroneOffsets', () => {
  it('gives no offset to a lone drone away from every Hub', () => {
    const offsets = computeDroneOffsets([drone('DRN-001', [18.7, 54.5])], [HUB])

    expect(offsets.size).toBe(0)
  })

  it('moves a lone drone off its Hub marker', () => {
    const offsets = computeDroneOffsets([drone('DRN-001', HUB_POINT)], [HUB])

    expect(offsets.get('DRN-001')).toBeDefined()
    expect(distance(offsets.get('DRN-001')!)).toBeGreaterThanOrEqual(40 / 2 + 24 / 2)
  })

  it('spreads drones that share a Hub location on a ring clear of the Hub marker', () => {
    const drones = ['DRN-001', 'DRN-002', 'DRN-003'].map((id) => drone(id, HUB_POINT))

    const offsets = computeDroneOffsets(drones, [HUB])

    const values = drones.map((d) => offsets.get(d.id)!)
    expect(new Set(values.map((v) => v.join(','))).size).toBe(3)
    values.forEach((v) => expect(distance(v)).toBeGreaterThanOrEqual(40 / 2 + 24 / 2))
    for (let i = 0; i < values.length; i++) {
      for (let j = i + 1; j < values.length; j++) {
        const gap = distance([values[i][0] - values[j][0], values[i][1] - values[j][1]])
        expect(gap).toBeGreaterThanOrEqual(24) // markers do not overlap each other
      }
    }
  })

  it('is deterministic and independent of the input order', () => {
    const ids = ['DRN-003', 'DRN-001', 'DRN-002']
    const forward = computeDroneOffsets(
      ids.map((id) => drone(id, HUB_POINT)),
      [HUB],
    )
    const reversed = computeDroneOffsets(
      [...ids].reverse().map((id) => drone(id, HUB_POINT)),
      [HUB],
    )

    expect([...forward].sort()).toEqual([...reversed].sort())
    expect(forward.get('DRN-001')![1]).toBeLessThan(0) // the first drone is placed at the top
  })

  it('spreads drones that share a location without a Hub', () => {
    const point: [number, number] = [18.5, 54.45]

    const offsets = computeDroneOffsets([drone('DRN-001', point), drone('DRN-002', point)], [])

    expect(offsets.size).toBe(2)
    expect(offsets.get('DRN-001')).not.toEqual(offsets.get('DRN-002'))
  })

  it('handles each location separately and never changes the drones', () => {
    const a = drone('DRN-001', HUB_POINT)
    const b = drone('DRN-002', HUB_POINT)
    const c = drone('DRN-003', [18.7, 54.5])
    const before = JSON.stringify([a, b, c])

    const offsets = computeDroneOffsets([a, b, c], [HUB])

    expect(offsets.has('DRN-003')).toBe(false)
    expect(offsets.has('DRN-001')).toBe(true)
    expect(JSON.stringify([a, b, c])).toBe(before)
  })
})

describe('droneMarkerLabel', () => {
  it('names the drone with its status and battery', () => {
    const flying = { ...drone('DRN-007', HUB_POINT), status: 'IN_FLIGHT' as const }
    expect(droneMarkerLabel(flying)).toBe('Drone DRN-007, In flight, battery 90%')
  })

  it('says a non-flying drone shown on the map is not at a Hub', () => {
    expect(droneMarkerLabel(drone('DRN-007', HUB_POINT))).toBe(
      'Drone DRN-007, Idle, battery 90%, not at a Hub',
    )
  })
})
