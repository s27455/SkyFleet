import { describe, expect, it, vi } from 'vitest'

import { DRONE_RESPONSES, SF1_MODEL_RESPONSE } from '../test/droneFixtures'
import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { getDrones } from './drones'

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('getDrones', () => {
  it('requests the drones endpoint and maps all twelve drones', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(DRONE_RESPONSES)))

    const drones = await getDrones()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/drones$/)
    expect(drones).toHaveLength(12)
    expect(drones.map((drone) => drone.id)).toEqual(DRONE_RESPONSES.map((drone) => drone.id))
  })

  it('maps identity, status, battery, Hub, real coordinates and the nested model', async () => {
    stubFetch(() => Promise.resolve(jsonResponse(DRONE_RESPONSES)))

    const [first] = await getDrones()

    expect(first).toEqual({
      id: 'DRN-001',
      hubId: 'hub-centrum-handlowe-osowa',
      status: 'IDLE',
      batteryPct: 100,
      coordinates: [18.49097, 54.42569], // [longitude, latitude], unchanged
      model: {
        id: 'SF-1',
        name: 'SkyFleet SF-1 Courier',
        airframeType: 'hexacopter',
        maxPayloadKg: 3,
        maxRangeKm: 20,
        recommendedMissionRangeKm: 14,
        cruiseSpeedKmh: 45,
        maxSpeedKmh: 60,
        nominalFlightTimeMin: 32,
        minBatteryReservePct: 20,
        chargeTo80Minutes: 45,
        maxWindMps: 10,
        emptyWeightKg: 9,
      },
    })
  })

  it('accepts an empty list', async () => {
    stubFetch(() => Promise.resolve(jsonResponse([])))

    await expect(getDrones()).resolves.toEqual([])
  })

  it('rejects with ApiError on an HTTP error status', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'boom' }, 500)))

    await expect(getDrones()).rejects.toMatchObject({ name: 'ApiError', status: 500 })
  })

  it('rejects with ApiError when the backend is unreachable', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))

    await expect(getDrones()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects with ApiError when a 200 response is not valid JSON', async () => {
    stubFetch(() => Promise.resolve(new Response('<html>proxy page</html>', { status: 200 })))

    await expect(getDrones()).rejects.toBeInstanceOf(ApiError)
  })

  const [valid] = DRONE_RESPONSES
  const withModel = (overrides: object) => [
    { ...valid, model: { ...SF1_MODEL_RESPONSE, ...overrides } },
  ]
  it.each([
    ['not a list', { drones: [] }],
    ['an item that is not an object', [null]],
    ['a missing id', [{ ...valid, id: undefined }]],
    ['a missing hub_id', [{ ...valid, hub_id: '' }]],
    ['an unknown status', [{ ...valid, status: 'FLYING' }]],
    ['a lowercase status', [{ ...valid, status: 'idle' }]],
    ['a battery below 0', [{ ...valid, battery_pct: -1 }]],
    ['a battery above 100', [{ ...valid, battery_pct: 101 }]],
    ['a fractional battery', [{ ...valid, battery_pct: 50.5 }]],
    ['a string longitude', [{ ...valid, longitude: '18.5' }]],
    ['a longitude out of range', [{ ...valid, longitude: 181 }]],
    ['a latitude out of range', [{ ...valid, latitude: 91 }]],
    ['a null latitude', [{ ...valid, latitude: null }]],
    ['a missing model', [{ ...valid, model: undefined }]],
    ['a model that is not an object', [{ ...valid, model: 'SF-1' }]],
    ['a model without a name', withModel({ name: '' })],
    ['a model without an airframe type', withModel({ airframe_type: '' })],
    ['a string maximum speed', withModel({ max_speed_kmh: '60' })],
    ['a zero charge time', withModel({ charge_to_80_minutes: 0 })],
    ['a negative wind limit', withModel({ max_wind_mps: -1 })],
    ['a missing empty weight', withModel({ empty_weight_kg: undefined })],
    ['a zero payload', withModel({ max_payload_kg: 0 })],
    ['a negative range', withModel({ max_range_km: -20 })],
    ['a string cruise speed', withModel({ cruise_speed_kmh: '45' })],
    ['a reserve above 100', withModel({ min_battery_reserve_pct: 101 })],
    ['duplicate ids', [valid, valid]],
  ])('rejects malformed data: %s', async (_name, payload) => {
    stubFetch(() => Promise.resolve(jsonResponse(payload)))

    await expect(getDrones()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects the whole list when a single record is invalid', async () => {
    stubFetch(() =>
      Promise.resolve(jsonResponse([DRONE_RESPONSES[0], { ...DRONE_RESPONSES[1], latitude: 999 }])),
    )

    await expect(getDrones()).rejects.toBeInstanceOf(ApiError)
  })
})
