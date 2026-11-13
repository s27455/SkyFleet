import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { disableAutoDispatch, enableAutoDispatch, getAutoDispatchStatus } from './dispatch'

const STATUS = {
  enabled: true,
  worker_running: true,
  last_check_at: '2026-11-12T10:00:00Z',
  last_outcome: 'Started 2 mission(s)',
}

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('automatic dispatch API', () => {
  it('reads and maps the server status', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(STATUS)))

    const status = await getAutoDispatchStatus()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/dispatch\/auto\/status$/)
    expect(status).toEqual({
      enabled: true,
      workerRunning: true,
      lastCheckAt: '2026-11-12T10:00:00Z',
      lastOutcome: 'Started 2 mission(s)',
    })
  })

  it('accepts a status without any pass yet', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ ...STATUS, enabled: false, last_check_at: null, last_outcome: null }),
      ),
    )

    expect(await getAutoDispatchStatus()).toMatchObject({ lastCheckAt: null, lastOutcome: null })
  })

  it('rejects malformed data instead of guessing', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ ...STATUS, enabled: 'yes' })))
    await expect(getAutoDispatchStatus()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.resolve(jsonResponse({ ...STATUS, last_check_at: 'yesterday' })))
    await expect(getAutoDispatchStatus()).rejects.toBeInstanceOf(ApiError)
  })

  it('POSTs enable and disable and maps the answer', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(STATUS)))

    await enableAutoDispatch()
    await disableAutoDispatch()

    const [enableCall, disableCall] = fetchMock.mock.calls
    expect(String(enableCall[0])).toMatch(/\/api\/dispatch\/auto\/enable$/)
    expect(enableCall[1]?.method).toBe('POST')
    expect(String(disableCall[0])).toMatch(/\/api\/dispatch\/auto\/disable$/)
    expect(disableCall[1]?.method).toBe('POST')
  })
})
