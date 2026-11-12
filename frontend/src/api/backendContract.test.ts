import { describe, expect, it, vi } from 'vitest'

import contract from '../test/backendContract.json'
import { jsonResponse } from '../test/hubFixtures'
import { getDrones } from './drones'
import { getFlights } from './flights'
import { getMissions } from './missions'
import { getOrders } from './orders'

/**
 * These payloads were captured from the real backend (Feature 010: a flight in the air, a simulated
 * emergency, an assigned mission, a delivered order, a drone in maintenance), not written by hand.
 * They guard the adapters against drift between the backend schemas and the frontend validation.
 */
function respondWith(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(jsonResponse(body))),
  )
}

describe('the frontend adapters accept the real backend responses', () => {
  it('reads the active flight with its worker status, target and snapshot age', async () => {
    respondWith(contract.flights_active)

    const snapshot = await getFlights()

    expect(snapshot.workerStale).toBe(false)
    const [flight] = snapshot.flights
    expect(flight.phase).toBe('OUTBOUND')
    expect(flight.missionStatus).toBe('IN_FLIGHT')
    expect(flight.target?.etaS).toBeGreaterThan(0)
    expect(flight.snapshotAgeS).toBeCloseTo(0.5, 1) // server_time minus updated_at
    expect(flight.emergency).toBeNull()
    expect(flight.batteryPct).toBe(98)
  })

  it('reads the emergency flight with its reason and stop position', async () => {
    respondWith(contract.flights_emergency)

    const [flight] = (await getFlights()).flights

    expect(flight.phase).toBe('EMERGENCY')
    expect(flight.missionStatus).toBe('EMERGENCY')
    expect(flight.target).toBeNull()
    expect(flight.deliveredAt).not.toBeNull()
    expect(flight.emergency?.reason).toBe('NO_HUB_WITH_CAPACITY')
    expect(flight.emergency?.position).toEqual(flight.position)
  })

  it('reads missions in every status the backend produced', async () => {
    respondWith(contract.missions)

    const missions = await getMissions()

    expect(missions.map((mission) => mission.status).sort()).toEqual([
      'ASSIGNED',
      'COMPLETED',
      'EMERGENCY',
    ])
    const assigned = missions.find((mission) => mission.status === 'ASSIGNED')
    expect(assigned?.id).toBe(contract.assigned_mission_id)
    expect(assigned?.totalKm).toBeGreaterThan(0)
  })

  it('reads orders including the delivery statuses', async () => {
    respondWith(contract.orders)

    const orders = await getOrders()

    expect(orders.filter((order) => order.status === 'DELIVERED').length).toBeGreaterThan(0)
    expect(orders).toHaveLength(10)
  })

  it('reads the drones, including one in maintenance away from a Hub', async () => {
    respondWith(contract.drones)

    const drones = await getDrones()

    expect(drones.some((drone) => drone.status === 'MAINTENANCE')).toBe(true)
    expect(drones).toHaveLength(12)
  })
})
