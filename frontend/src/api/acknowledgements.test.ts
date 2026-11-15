import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { acknowledgeEmergency } from './acknowledgements'
import { ApiError } from './client'

afterEach(() => vi.unstubAllGlobals())

const OK = { mission_id: 'MIS-1', acknowledged_at: '2026-11-15T10:05:00Z' }

function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
    Promise.resolve(jsonResponse(body, status)),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('acknowledgeEmergency', () => {
  it('posts to the mission with no body and maps the answer', async () => {
    const fetchMock = respondWith(OK)

    expect(await acknowledgeEmergency('MIS-1')).toEqual({
      missionId: 'MIS-1',
      acknowledgedAt: '2026-11-15T10:05:00Z',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/incidents\/emergencies\/MIS-1\/acknowledge$/)
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeUndefined()
  })

  it('encodes the mission id in the path', async () => {
    const fetchMock = respondWith({ ...OK, mission_id: 'MIS/1 x' })

    await acknowledgeEmergency('MIS/1 x')

    expect(String(fetchMock.mock.calls[0][0])).toContain('/emergencies/MIS%2F1%20x/acknowledge')
  })

  it('rejects an answer for another mission, a bad time and a non-object', async () => {
    respondWith({ ...OK, mission_id: 'MIS-2' })
    await expect(acknowledgeEmergency('MIS-1')).rejects.toBeInstanceOf(ApiError)

    respondWith({ ...OK, acknowledged_at: 'later' })
    await expect(acknowledgeEmergency('MIS-1')).rejects.toBeInstanceOf(ApiError)

    respondWith({ ...OK, acknowledged_at: '2026-11-15T10:05:00' }) // no time zone
    await expect(acknowledgeEmergency('MIS-1')).rejects.toBeInstanceOf(ApiError)

    respondWith('ok')
    await expect(acknowledgeEmergency('MIS-1')).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects with the backend status and detail when the alert does not exist', async () => {
    respondWith({ detail: { code: 'EMERGENCY_NOT_FOUND', message: 'No alert.' } }, 404)

    await expect(acknowledgeEmergency('MIS-9')).rejects.toMatchObject({
      status: 404,
      detail: { code: 'EMERGENCY_NOT_FOUND' },
    })
  })

  it('rejects on a server error, for example before the database is migrated', async () => {
    respondWith({ detail: 'Internal Server Error' }, 500)

    await expect(acknowledgeEmergency('MIS-1')).rejects.toMatchObject({ status: 500 })
  })

  it('rejects when the network fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )

    await expect(acknowledgeEmergency('MIS-1')).rejects.toBeInstanceOf(ApiError)
  })
})
