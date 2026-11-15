import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import {
  disableRandomIncidents,
  enableRandomIncidents,
  getRandomIncidents,
  isWorkerUnavailable,
  toRandomIncidentsStatus,
} from './randomIncidents'

afterEach(() => vi.unstubAllGlobals())

const OK = {
  enabled: true,
  worker_running: true,
  last_check_at: '2026-11-12T10:03:00Z',
  last_outcome: 'Triggered: LPR helicopter started',
}

describe('random incidents API', () => {
  it('maps a valid answer to the UI model', () => {
    expect(toRandomIncidentsStatus(OK)).toEqual({
      enabled: true,
      workerRunning: true,
      lastCheckAt: '2026-11-12T10:03:00Z',
      lastOutcome: 'Triggered: LPR helicopter started',
    })
    expect(
      toRandomIncidentsStatus({ ...OK, enabled: false, last_check_at: null, last_outcome: null }),
    ).toMatchObject({ enabled: false, lastCheckAt: null, lastOutcome: null })
  })

  it.each([
    ['not an object', 'x'],
    ['null', null],
    ['bad enabled', { ...OK, enabled: 'yes' }],
    ['bad worker_running', { ...OK, worker_running: 1 }],
    ['bad last_check_at', { ...OK, last_check_at: 'yesterday' }],
    ['zone-less last_check_at', { ...OK, last_check_at: '2026-11-12T10:03:00' }],
    ['bad last_outcome', { ...OK, last_outcome: 5 }],
    ['missing fields', {}],
  ])('rejects %s', (_name, payload) => {
    expect(() => toRandomIncidentsStatus(payload)).toThrow(ApiError)
  })

  it('reads the status with GET', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse(OK)),
    )
    vi.stubGlobal('fetch', fetchMock)

    expect((await getRandomIncidents()).enabled).toBe(true)

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/random$/)
  })

  it('enables and disables with POST and no body', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse(OK)),
    )
    vi.stubGlobal('fetch', fetchMock)

    await enableRandomIncidents()
    await disableRandomIncidents()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/random\/enable$/)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/incidents\/random\/disable$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
  })

  it('recognises the stable 503 worker code only', () => {
    const detail = { code: 'SIMULATION_WORKER_UNAVAILABLE', message: 'x' }
    expect(isWorkerUnavailable(new ApiError('x', 503, detail))).toBe(true)
    expect(isWorkerUnavailable(new ApiError('x', 503, { code: 'OTHER' }))).toBe(false)
    expect(isWorkerUnavailable(new ApiError('x', 500, detail))).toBe(false)
    expect(isWorkerUnavailable(new ApiError('x', 503))).toBe(false)
    expect(isWorkerUnavailable(new Error('x'))).toBe(false)
  })
})
