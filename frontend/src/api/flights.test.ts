import { describe, expect, it, vi } from 'vitest'

import { EMERGENCY_FLIGHT, OUTBOUND_FLIGHT, flightsResponse } from '../test/flightFixtures'
import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { getFlights } from './flights'

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const respondWith = (body: unknown) => stubFetch(() => Promise.resolve(jsonResponse(body)))

describe('getFlights', () => {
  it('requests the flights endpoint and maps the snapshot with the worker status', async () => {
    const fetchMock = respondWith(flightsResponse([OUTBOUND_FLIGHT]))

    const snapshot = await getFlights()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/flights$/)
    expect(snapshot.serverTime).toBe('2026-11-12T10:00:10Z')
    expect(snapshot.workerHeartbeatAt).toBe('2026-11-12T10:00:09Z')
    expect(snapshot.workerStale).toBe(false)
    expect(snapshot.flights).toHaveLength(1)
  })

  it('maps a flight with its real position, target and snapshot age', async () => {
    respondWith(flightsResponse([OUTBOUND_FLIGHT]))

    const [flight] = (await getFlights()).flights

    expect(flight).toEqual({
      missionId: 'MIS-AAAA0001',
      orderId: 'ORD-001',
      droneId: 'DRN-010',
      missionStatus: 'IN_FLIGHT',
      phase: 'OUTBOUND',
      progress: 0.25,
      position: [18.599, 54.38], // [longitude, latitude], unchanged
      batteryPct: 98,
      target: { position: [18.5972, 54.3768], etaS: 10 },
      originHubId: 'hub-galeria-baltycka',
      plannedReturnHubId: 'hub-galeria-baltycka',
      landingTargetHubId: 'hub-galeria-baltycka',
      startedAt: '2026-11-12T10:00:00Z',
      deliveredAt: null,
      recalledAt: null,
      failedAt: null,
      updatedAt: '2026-11-12T10:00:09Z',
      snapshotAgeS: 1, // server_time minus updated_at, both on the backend's clock
      emergency: null,
    })
  })

  it('maps the recall time of a flight whose order was cancelled in flight', async () => {
    respondWith(
      flightsResponse([
        { ...OUTBOUND_FLIGHT, phase: 'RETURNING', recalled_at: '2026-11-12T10:00:08Z' },
      ]),
    )

    const [flight] = (await getFlights()).flights

    expect(flight.recalledAt).toBe('2026-11-12T10:00:08Z')
    expect(flight.deliveredAt).toBeNull()
  })

  it('rejects a recall time without a zone', async () => {
    respondWith(flightsResponse([{ ...OUTBOUND_FLIGHT, recalled_at: '2026-11-12T10:00:08' }]))

    await expect(getFlights()).rejects.toThrow(/recalled_at/)
  })

  it('maps an emergency flight without a target', async () => {
    respondWith(flightsResponse([EMERGENCY_FLIGHT]))

    const [flight] = (await getFlights()).flights

    expect(flight.phase).toBe('EMERGENCY')
    expect(flight.target).toBeNull()
    expect(flight.emergency).toEqual({
      reason: 'NO_HUB_WITH_CAPACITY',
      at: '2026-11-12T10:00:09Z',
      position: [18.6012, 54.3821],
    })
    expect(flight.deliveredAt).toBe('2026-11-12T10:00:03Z')
  })

  it('accepts no flights, and a worker that never sent a heartbeat', async () => {
    respondWith(flightsResponse([], { worker_heartbeat_at: null, worker_stale: true }))

    const snapshot = await getFlights()

    expect(snapshot.flights).toEqual([])
    expect(snapshot.workerHeartbeatAt).toBeNull()
    expect(snapshot.workerStale).toBe(true)
  })

  it('never reports a negative snapshot age', async () => {
    respondWith(flightsResponse([{ ...OUTBOUND_FLIGHT, updated_at: '2026-11-12T10:00:30Z' }]))

    expect((await getFlights()).flights[0].snapshotAgeS).toBe(0)
  })

  const bad = (patch: Record<string, unknown>) => ({ ...OUTBOUND_FLIGHT, ...patch })

  it.each<[string, unknown]>([
    ['an unknown phase', bad({ phase: 'WARP' })],
    ['an unknown mission status', bad({ mission_status: 'FLYING' })],
    ['progress above 1', bad({ progress: 1.5 })],
    ['a battery above 100', bad({ battery_pct: 101 })],
    ['a missing drone id', bad({ drone_id: '' })],
    ['a missing mission id', bad({ mission_id: '' })],
    ['a position with three numbers', bad({ position: [18.6, 54.4, 10] })],
    ['a latitude out of range', bad({ position: [18.6, 91] })],
    ['a string coordinate', bad({ position: ['18.6', 54.4] })],
    ['a start time without a time zone', bad({ started_at: '2026-11-12T10:00:00' })],
    ['an unparseable update time', bad({ updated_at: 'yesterday' })],
    ['a negative target eta', bad({ target: { position: [18.6, 54.4], eta_s: -1 } })],
    ['a target with a bad position', bad({ target: { position: [18.6], eta_s: 1 } })],
    [
      'an unknown emergency reason',
      bad({ emergency: { reason: 'CRASH', at: '2026-11-12T10:00:09Z', position: [18.6, 54.4] } }),
    ],
    [
      'an emergency without a time',
      bad({ emergency: { reason: 'BATTERY_CRITICAL', at: 'soon', position: [18.6, 54.4] } }),
    ],
    ['a non-object flight', 42],
  ])('rejects the whole response for %s', async (_name, flight) => {
    respondWith(flightsResponse([OUTBOUND_FLIGHT, flight as never]))

    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects a malformed envelope', async () => {
    respondWith([OUTBOUND_FLIGHT]) // the old plain-list shape is not the contract
    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)

    respondWith({ ...flightsResponse(), worker_stale: 'no' })
    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)

    respondWith({ ...flightsResponse(), server_time: 'now' })
    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)

    respondWith({ ...flightsResponse(), flights: {} })
    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)

    respondWith(flightsResponse([OUTBOUND_FLIGHT, OUTBOUND_FLIGHT]))
    await expect(getFlights()).rejects.toThrow(/duplicate/)
  })

  it('rejects on a server error and on a network failure', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'oops' }, 500)))
    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    await expect(getFlights()).rejects.toBeInstanceOf(ApiError)
  })
})
