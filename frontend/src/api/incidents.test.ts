import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import {
  getLprStatus,
  isLprAlreadyActive,
  isNoEligibleTarget,
  triggerDroneFailure,
  triggerLprHelicopter,
  triggerRecipientUnavailable,
} from './incidents'

afterEach(() => vi.unstubAllGlobals())

const RESULT = {
  drone_id: 'DRN-010',
  mission_id: 'MIS-AAAA0001',
  order_id: 'ORD-001',
  stage: 'BEFORE_DELIVERY',
  landing_position: [18.6, 54.38],
}

describe('triggerDroneFailure', () => {
  it('posts to the endpoint without a body and maps the answer', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse(RESULT)),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await triggerDroneFailure()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/drone-failure$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
    expect(result).toEqual({
      droneId: 'DRN-010',
      missionId: 'MIS-AAAA0001',
      orderId: 'ORD-001',
      stage: 'BEFORE_DELIVERY',
      landingPosition: [18.6, 54.38],
    })
  })

  it('rejects an answer without a usable landing position', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ ...RESULT, landing_position: [18.6] }))),
    )

    await expect(triggerDroneFailure()).rejects.toBeInstanceOf(ApiError)
  })

  it('recognises the clear "no eligible target" answer and nothing else', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'NO_ELIGIBLE_TARGET', message: 'Nothing flies' } }, 409),
        ),
      ),
    )
    const none = await triggerDroneFailure().catch((error: unknown) => error)

    expect(isNoEligibleTarget(none)).toBe(true)
    expect(isNoEligibleTarget(new ApiError('Backend is unreachable'))).toBe(false)
    expect(isNoEligibleTarget(new ApiError('x', 409, { code: 'OTHER' }))).toBe(false)
    expect(isNoEligibleTarget(new Error('x'))).toBe(false)
  })
})

describe('triggerRecipientUnavailable', () => {
  const PENDING = {
    drone_id: 'DRN-010',
    mission_id: 'MIS-AAAA0001',
    order_id: 'ORD-001',
    attempt_at: '2026-11-13T12:00:20Z',
  }

  it('posts to the endpoint without a body and maps the pending answer', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse(PENDING)),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await triggerRecipientUnavailable()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/recipient-unavailable$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
    expect(result).toEqual({
      droneId: 'DRN-010',
      missionId: 'MIS-AAAA0001',
      orderId: 'ORD-001',
      attemptAt: '2026-11-13T12:00:20Z',
    })
  })

  it('rejects an answer without a usable attempt time', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ ...PENDING, attempt_at: 'soon' }))),
    )

    await expect(triggerRecipientUnavailable()).rejects.toBeInstanceOf(ApiError)
  })

  it('surfaces the clear "no eligible target" answer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'NO_ELIGIBLE_TARGET', message: 'Nothing' } }, 409),
        ),
      ),
    )

    const none = await triggerRecipientUnavailable().catch((error: unknown) => error)

    expect(isNoEligibleTarget(none)).toBe(true)
  })
})

const LPR = {
  id: 'LPR-ABCD1234',
  status: 'ACTIVE',
  origin: 'MANUAL',
  started_at: '2026-11-13T12:00:00Z',
  ends_at: '2026-11-13T12:03:00Z',
  position: [18.5, 54.3925],
  route_start: [18.46, 54.3925],
  route_end: [18.67, 54.3925],
  speed_ms: 80,
  radius_m: 500,
  hold_margin_m: 250,
}

describe('LPR helicopter (Feature 018E)', () => {
  it('posts without a body and maps the scenario', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse(LPR)),
    )
    vi.stubGlobal('fetch', fetchMock)

    const scenario = await triggerLprHelicopter()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/lpr-helicopter$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
    expect(scenario).toEqual({
      id: 'LPR-ABCD1234',
      startedAt: '2026-11-13T12:00:00Z',
      endsAt: '2026-11-13T12:03:00Z',
      position: [18.5, 54.3925],
      routeStart: [18.46, 54.3925],
      routeEnd: [18.67, 54.3925],
      speedMs: 80,
      radiusM: 500,
      holdMarginM: 250,
    })
  })

  it.each([
    ['a position outside the globe', { ...LPR, position: [200, 54] }],
    ['a zone without a radius', { ...LPR, radius_m: 0 }],
    ['a zone-less time', { ...LPR, ends_at: '2026-11-13 12:03:00' }],
    ['a route with one point', { ...LPR, route_end: [18.67] }],
  ])('rejects %s', async (_name, body) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(body))),
    )

    await expect(triggerLprHelicopter()).rejects.toBeInstanceOf(ApiError)
  })

  it('reads the status: a running scenario, or none', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse({ server_time: '2026-11-13T12:00:10Z', scenario: LPR })),
      ),
    )
    expect((await getLprStatus()).scenario?.id).toBe('LPR-ABCD1234')

    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse({ server_time: '2026-11-13T12:05:00Z', scenario: null })),
      ),
    )
    expect(await getLprStatus()).toEqual({ scenario: null })
  })

  it('recognises the clear "already active" answer and nothing else', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'LPR_ALREADY_ACTIVE', message: 'Already' } }, 409),
        ),
      ),
    )
    const active = await triggerLprHelicopter().catch((error: unknown) => error)

    expect(isLprAlreadyActive(active)).toBe(true)
    expect(isLprAlreadyActive(new ApiError('x', 409, { code: 'NO_ELIGIBLE_TARGET' }))).toBe(false)
    expect(isLprAlreadyActive(new ApiError('Backend is unreachable'))).toBe(false)
  })
})
