import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import {
  disableOrderSimulation,
  enableOrderSimulation,
  getOrderSimulationStatus,
  toOrderSimulationStatus,
} from './orderSimulation'

const STATUS = {
  enabled: true,
  worker_running: true,
  last_check_at: '2026-11-12T10:00:00Z',
  last_outcome: 'Created ORD-1: ul. Długa 45, Gdańsk, 1.2 kg',
  outstanding_orders: 4,
  max_outstanding_orders: 20,
}

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('toOrderSimulationStatus', () => {
  it('maps a valid status', () => {
    expect(toOrderSimulationStatus(STATUS)).toEqual({
      enabled: true,
      workerRunning: true,
      lastCheckAt: '2026-11-12T10:00:00Z',
      lastOutcome: 'Created ORD-1: ul. Długa 45, Gdańsk, 1.2 kg',
      outstandingOrders: 4,
      maxOutstandingOrders: 20,
    })
  })

  it('accepts a status that has never run (null time and outcome)', () => {
    const status = toOrderSimulationStatus({ ...STATUS, last_check_at: null, last_outcome: null })

    expect(status.lastCheckAt).toBeNull()
    expect(status.lastOutcome).toBeNull()
  })

  it.each([
    ['a non-object', 42],
    ['null', null],
    ['a bad enabled', { ...STATUS, enabled: 'yes' }],
    ['a bad worker_running', { ...STATUS, worker_running: undefined }],
    ['a time without a zone', { ...STATUS, last_check_at: '2026-11-12T10:00:00' }],
    ['a bad outcome', { ...STATUS, last_outcome: 5 }],
    ['a negative count', { ...STATUS, outstanding_orders: -1 }],
    ['a fractional count', { ...STATUS, outstanding_orders: 1.5 }],
    ['a missing limit', { ...STATUS, max_outstanding_orders: undefined }],
  ])('rejects %s', (_name, payload) => {
    expect(() => toOrderSimulationStatus(payload)).toThrow(ApiError)
  })
})

describe('order simulation calls', () => {
  it('reads the status with GET', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(STATUS)))

    const status = await getOrderSimulationStatus()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\/simulation\/status$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined()
    expect(status.outstandingOrders).toBe(4)
  })

  it('enables and disables with POST and returns the server status', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(STATUS)))

    await enableOrderSimulation()
    await disableOrderSimulation()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\/simulation\/enable$/)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/orders\/simulation\/disable$/)
    expect(fetchMock.mock.calls.map(([, init]) => init?.method)).toEqual(['POST', 'POST'])
  })

  it('rejects with the HTTP status when the worker is unavailable', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: { message: 'no worker' } }, 503)))

    await expect(enableOrderSimulation()).rejects.toMatchObject({ status: 503 })
  })
})
