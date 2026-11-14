import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { RelocateError, getRelocationPlan, relocateDrone } from './relocation'

const PLAN = {
  drone_id: 'DRN-010',
  eligible: true,
  reasons: [],
  origin_hub_id: 'hub-galeria-baltycka',
  destination_hub_id: 'hub-forum-gdansk',
  distance_km: 4.6,
  distance_budget_km: 14,
  required_battery_pct: 43,
  expected_battery_use_pct: 23,
  drone_battery_pct: 100,
  destination_docked_drones: 3,
  destination_capacity: 50,
  warnings: ['The destination is not reserved.'],
}

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('getRelocationPlan', () => {
  it('requests the read-only plan and maps it', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(PLAN)))

    const plan = await getRelocationPlan('DRN-010', 'hub-forum-gdansk')

    expect(String(fetchMock.mock.calls[0][0])).toMatch(
      /\/api\/drones\/DRN-010\/relocation-plan\?destination_hub_id=hub-forum-gdansk$/,
    )
    expect(plan).toMatchObject({
      droneId: 'DRN-010',
      eligible: true,
      originHubId: 'hub-galeria-baltycka',
      destinationHubId: 'hub-forum-gdansk',
      distanceKm: 4.6,
      expectedBatteryUsePct: 23,
      destinationDockedDrones: 3,
      warnings: ['The destination is not reserved.'],
    })
  })

  it('keeps the reasons of an ineligible plan and an unknown origin', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({
          ...PLAN,
          eligible: false,
          origin_hub_id: null,
          reasons: [{ code: 'DRONE_NOT_AT_HUB', message: 'Drone is not docked at a Hub.' }],
        }),
      ),
    )

    const plan = await getRelocationPlan('DRN-010', 'hub-forum-gdansk')

    expect(plan.originHubId).toBeNull()
    expect(plan.reasons).toEqual([
      { code: 'DRONE_NOT_AT_HUB', message: 'Drone is not docked at a Hub.' },
    ])
  })

  it('rejects data that is not a plan', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ ...PLAN, distance_km: 'far' })))

    await expect(getRelocationPlan('DRN-010', 'hub-forum-gdansk')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('relocateDrone', () => {
  const STARTED = {
    mission_id: 'MIS-RELOC001',
    drone_id: 'DRN-010',
    origin_hub_id: 'hub-galeria-baltycka',
    destination_hub_id: 'hub-forum-gdansk',
    started_at: '2026-11-12T10:00:00Z',
    distance_km: 4.6,
  }

  it('posts the destination and maps the started relocation', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(STARTED, 201)))

    const started = await relocateDrone('DRN-010', 'hub-forum-gdansk')

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/drones\/DRN-010\/relocate$/)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ destination_hub_id: 'hub-forum-gdansk' })
    expect(started).toEqual({
      missionId: 'MIS-RELOC001',
      droneId: 'DRN-010',
      originHubId: 'hub-galeria-baltycka',
      destinationHubId: 'hub-forum-gdansk',
    })
  })

  it('explains an ineligible drone with the backend reasons', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse(
          {
            detail: {
              code: 'RELOCATION_NOT_ELIGIBLE',
              message: 'x',
              plan: { reasons: [{ code: 'SAME_HUB', message: 'Choose a different Hub.' }] },
            },
          },
          409,
        ),
      ),
    )

    const error = await relocateDrone('DRN-010', 'hub-galeria-baltycka').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(RelocateError)
    expect((error as RelocateError).reasons).toEqual(['Choose a different Hub.'])
  })

  it('says when the worker is not running', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ detail: { code: 'SIMULATION_WORKER_UNAVAILABLE', message: 'x' } }, 503),
      ),
    )

    await expect(relocateDrone('DRN-010', 'hub-forum-gdansk')).rejects.toThrow(
      /simulation worker is not running/,
    )
  })

  it('says when the backend is unreachable', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))

    await expect(relocateDrone('DRN-010', 'hub-forum-gdansk')).rejects.toThrow(/unreachable/)
  })
})
