import { describe, expect, it } from 'vitest'

import type { Drone, DroneStatus } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { DOCK_RADIUS_M, distanceMeters, partitionFleet } from './fleetPlacement'

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

const HUB_A: Hub = {
  id: 'hub-a',
  name: 'Hub A',
  address: 'Ulica A 1',
  coordinates: [18.6, 54.4],
  droneCapacity: 50,
}
const HUB_B: Hub = { ...HUB_A, id: 'hub-b', name: 'Hub B', coordinates: [18.5, 54.5] }

function drone(
  id: string,
  coordinates: [number, number],
  status: DroneStatus = 'IDLE',
  hubId = 'hub-a',
): Drone {
  return { id, hubId, status, batteryPct: 90, coordinates, model: MODEL }
}

/** A point roughly `meters` due north of a Hub (1 degree of latitude is about 111.2 km). */
const northOf = ([lng, lat]: [number, number], meters: number): [number, number] => [
  lng,
  lat + meters / 111_195,
]

describe('distanceMeters', () => {
  it('is zero for the same point and about 111 km per degree of latitude', () => {
    expect(distanceMeters([18.6, 54.4], [18.6, 54.4])).toBe(0)
    expect(distanceMeters([18.6, 54.4], [18.6, 55.4])).toBeCloseTo(111_195, -2)
  })
})

describe('partitionFleet', () => {
  it('docks non-flying drones at the Hub they are at', () => {
    const { dockedByHub, markerDrones } = partitionFleet(
      [drone('DRN-002', HUB_A.coordinates), drone('DRN-001', HUB_A.coordinates)],
      [HUB_A, HUB_B],
    )

    expect(dockedByHub.get('hub-a')?.map((d) => d.id)).toEqual(['DRN-001', 'DRN-002'])
    expect(dockedByHub.has('hub-b')).toBe(false)
    expect(markerDrones).toEqual([])
  })

  it.each<DroneStatus>(['IDLE', 'CHARGING', 'MAINTENANCE'])(
    'docks a %s drone at a Hub',
    (status) => {
      const { dockedByHub } = partitionFleet([drone('DRN-001', HUB_A.coordinates, status)], [HUB_A])

      expect(dockedByHub.get('hub-a')).toHaveLength(1)
    },
  )

  it('never docks an IN_FLIGHT drone, even exactly over a Hub', () => {
    const flying = drone('DRN-001', HUB_A.coordinates, 'IN_FLIGHT')

    const { dockedByHub, markerDrones } = partitionFleet([flying], [HUB_A])

    expect(dockedByHub.size).toBe(0)
    expect(markerDrones).toEqual([flying])
  })

  it('uses a 50 m radius around the Hub', () => {
    expect(DOCK_RADIUS_M).toBe(50)
    const inside = drone('DRN-001', northOf(HUB_A.coordinates, 45))
    const outside = drone('DRN-002', northOf(HUB_A.coordinates, 60))

    const { dockedByHub, markerDrones } = partitionFleet([inside, outside], [HUB_A])

    expect(dockedByHub.get('hub-a')).toEqual([inside])
    expect(markerDrones).toEqual([outside])
  })

  it('keeps a non-flying drone away from every Hub as an individual marker (never hidden)', () => {
    const parked = drone('DRN-001', [18.55, 54.45], 'MAINTENANCE')

    const { dockedByHub, markerDrones } = partitionFleet([parked], [HUB_A, HUB_B])

    expect(dockedByHub.size).toBe(0)
    expect(markerDrones).toEqual([parked])
  })

  it('counts a drone where it is, not at its assigned home Hub', () => {
    const landedElsewhere = drone('DRN-001', HUB_B.coordinates, 'IDLE', 'hub-a')

    const { dockedByHub } = partitionFleet([landedElsewhere], [HUB_A, HUB_B])

    expect(dockedByHub.get('hub-b')).toEqual([landedElsewhere])
    expect(dockedByHub.has('hub-a')).toBe(false)
  })

  it('picks the nearest Hub when two Hubs are within range', () => {
    const near: Hub = { ...HUB_B, id: 'hub-near', coordinates: northOf(HUB_A.coordinates, 30) }
    const d = drone('DRN-001', northOf(HUB_A.coordinates, 25))

    const { dockedByHub } = partitionFleet([d], [HUB_A, near])

    expect(dockedByHub.get('hub-near')).toEqual([d])
  })

  it('resolves two Hubs at the same distance by Hub id, whatever the input order', () => {
    const first: Hub = { ...HUB_A, id: 'hub-1', coordinates: [18.6, 54.4] }
    const second: Hub = { ...HUB_A, id: 'hub-2', coordinates: [18.6, 54.4] }
    const d = drone('DRN-001', [18.6, 54.4])

    expect(partitionFleet([d], [second, first]).dockedByHub.has('hub-1')).toBe(true)
    expect(partitionFleet([d], [first, second]).dockedByHub.has('hub-1')).toBe(true)
  })

  it('measures distance along longitude too', () => {
    // About 65 m east at latitude 54.4 (1 degree of longitude is about 64.8 km there).
    const east = drone('DRN-001', [HUB_A.coordinates[0] + 0.001, HUB_A.coordinates[1]])

    expect(distanceMeters(east.coordinates, HUB_A.coordinates)).toBeGreaterThan(60)
    expect(partitionFleet([east], [HUB_A]).markerDrones).toEqual([east])
  })

  it('shows every drone as a marker when no Hub is known, and changes no drone', () => {
    const drones = [drone('DRN-001', HUB_A.coordinates), drone('DRN-002', HUB_B.coordinates)]
    const before = JSON.stringify(drones)

    const { dockedByHub, markerDrones } = partitionFleet(drones, [])

    expect(dockedByHub.size).toBe(0)
    expect(markerDrones).toEqual(drones)
    expect(JSON.stringify(drones)).toBe(before)
  })
})
