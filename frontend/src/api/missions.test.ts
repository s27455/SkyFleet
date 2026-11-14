import { describe, expect, it, vi } from 'vitest'

import { ASSIGNED_MISSION } from '../test/flightFixtures'
import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { StartMissionError, getMissions, startMission } from './missions'

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('getMissions', () => {
  it('requests the missions endpoint and maps each mission', async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve(jsonResponse([ASSIGNED_MISSION, { ...ASSIGNED_MISSION, id: 'MIS-2' }])),
    )

    const missions = await getMissions()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/missions$/)
    expect(missions[0]).toEqual({
      id: 'MIS-AAAA0001',
      orderId: 'ORD-001',
      purpose: 'DELIVERY',
      droneId: 'DRN-010',
      originHubId: 'hub-galeria-baltycka',
      returnHubId: 'hub-galeria-baltycka',
      status: 'ASSIGNED',
      totalKm: 1.372,
    })
    expect(missions).toHaveLength(2)
  })

  it('accepts an empty list and every mission status', async () => {
    stubFetch(() => Promise.resolve(jsonResponse([])))
    await expect(getMissions()).resolves.toEqual([])

    for (const status of ['ASSIGNED', 'IN_FLIGHT', 'CANCELLED', 'COMPLETED', 'EMERGENCY']) {
      stubFetch(() => Promise.resolve(jsonResponse([{ ...ASSIGNED_MISSION, status }])))
      await expect(getMissions()).resolves.toHaveLength(1)
    }
  })

  it.each<[string, Record<string, unknown>]>([
    ['an unknown status', { status: 'PAUSED' }],
    ['a missing id', { id: '' }],
    ['a missing order', { order_id: '' }],
    ['a missing return Hub', { return_hub_id: '' }],
    ['a negative distance', { total_km: -1 }],
    ['a string distance', { total_km: '1.4' }],
  ])('rejects the whole list for %s', async (_name, patch) => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse([
          { ...ASSIGNED_MISSION, id: 'MIS-OK' },
          { ...ASSIGNED_MISSION, ...patch },
        ]),
      ),
    )

    await expect(getMissions()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects a non-list payload, a non-object item and duplicate ids', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ missions: [] })))
    await expect(getMissions()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.resolve(jsonResponse([42])))
    await expect(getMissions()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.resolve(jsonResponse([ASSIGNED_MISSION, ASSIGNED_MISSION])))
    await expect(getMissions()).rejects.toThrow(/duplicate/)
  })
})

describe('startMission', () => {
  const failWith = (status: number, detail: unknown) =>
    stubFetch(() => Promise.resolve(jsonResponse({ detail }, status)))

  it('posts to the mission start endpoint and returns the started mission', async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve(jsonResponse({ ...ASSIGNED_MISSION, status: 'IN_FLIGHT' })),
    )

    const mission = await startMission('MIS-AAAA0001')

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/missions\/MIS-AAAA0001\/start$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(mission.status).toBe('IN_FLIGHT')
  })

  it('encodes the mission id in the path', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ASSIGNED_MISSION)))

    await startMission('MIS/1 ?')

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/missions\/MIS%2F1%20%3F\/start$/)
  })

  it('explains that the simulation worker is not running (503)', async () => {
    failWith(503, { code: 'SIMULATION_WORKER_UNAVAILABLE', message: 'no heartbeat' })

    const error = await startMission('MIS-1').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(StartMissionError)
    expect((error as StartMissionError).failure).toBe('WORKER_UNAVAILABLE')
    expect((error as StartMissionError).message).toMatch(/worker is not running/)
    expect((error as StartMissionError).message).toMatch(/app\.worker/)
  })

  it('says the mission can no longer be started, naming its status (409)', async () => {
    failWith(409, { code: 'MISSION_NOT_STARTABLE', message: 'x', status: 'IN_FLIGHT' })

    const error = (await startMission('MIS-1').catch(
      (caught: unknown) => caught,
    )) as StartMissionError

    expect(error.failure).toBe('NOT_STARTABLE')
    expect(error.message).toMatch(/IN_FLIGHT/)
  })

  it('carries the backend reasons when the mission is no longer eligible (409)', async () => {
    failWith(409, {
      code: 'MISSION_NOT_ELIGIBLE',
      message: 'x',
      plan: {
        reasons: [
          { code: 'INSUFFICIENT_BATTERY', message: 'Drone battery is 10%.' },
          { code: 'BAD', nomessage: true },
          'junk',
        ],
      },
    })

    const error = (await startMission('MIS-1').catch(
      (caught: unknown) => caught,
    )) as StartMissionError

    expect(error.failure).toBe('NOT_ELIGIBLE')
    expect(error.reasons).toEqual(['Drone battery is 10%.']) // untrusted reasons are filtered
  })

  it('maps an unknown mission, other server errors and an unreachable backend', async () => {
    failWith(404, 'Mission not found')
    expect(
      ((await startMission('MIS-1').catch((c: unknown) => c)) as StartMissionError).failure,
    ).toBe('NOT_FOUND')

    failWith(500, undefined)
    expect(
      ((await startMission('MIS-1').catch((c: unknown) => c)) as StartMissionError).failure,
    ).toBe('UNKNOWN')

    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(
      ((await startMission('MIS-1').catch((c: unknown) => c)) as StartMissionError).failure,
    ).toBe('UNREACHABLE')
  })

  it('does not call a success with unexpected data a success', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ id: 'MIS-1' })))

    const error = (await startMission('MIS-1').catch(
      (caught: unknown) => caught,
    )) as StartMissionError

    expect(error).toBeInstanceOf(StartMissionError)
    expect(error.failure).toBe('UNKNOWN')
  })
})

describe('getMissions with a relocation (Feature 019A)', () => {
  const RELOCATION = {
    ...ASSIGNED_MISSION,
    order_id: null,
    purpose: 'RELOCATION',
    status: 'IN_FLIGHT',
  }

  it('maps a relocation without an order', async () => {
    stubFetch(() => Promise.resolve(jsonResponse([RELOCATION])))

    const [mission] = await getMissions()

    expect(mission.orderId).toBeNull()
    expect(mission.purpose).toBe('RELOCATION')
  })

  it('rejects a delivery without an order and a relocation with one', async () => {
    stubFetch(() => Promise.resolve(jsonResponse([{ ...ASSIGNED_MISSION, order_id: null }])))
    await expect(getMissions()).rejects.toThrow(/missing order_id/)

    stubFetch(() => Promise.resolve(jsonResponse([{ ...RELOCATION, order_id: 'ORD-001' }])))
    await expect(getMissions()).rejects.toThrow(/relocation must not have an order_id/)
  })
})
