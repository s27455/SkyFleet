import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { isNoEligibleTarget, triggerDroneFailure } from './incidents'

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
