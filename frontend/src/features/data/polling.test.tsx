import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { useDrones } from '../drones/useDrones'
import { useFlights } from '../flights/useFlights'
import { useMissions } from '../missions/useMissions'
import { useOrders } from '../orders/useOrders'
import { POLL_INTERVALS_MS } from './polling'

describe('the polling intervals', () => {
  it('are one second for flights and two for drones, orders and missions', async () => {
    vi.resetModules() // the test setup switches polling off in the shared instance
    const fresh = await import('./polling')

    expect(fresh.POLL_INTERVALS_MS).toEqual({ flights: 1000, fleet: 2000 })
    expect(fresh.REQUEST_TIMEOUT_MS.value).toBe(10_000)
  })
})

describe('the live hooks use those intervals', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    POLL_INTERVALS_MS.flights = null
    POLL_INTERVALS_MS.fleet = null
    vi.useRealTimers()
  })

  it('flights are read every second, and drones, orders and missions every two', async () => {
    POLL_INTERVALS_MS.flights = 1000
    POLL_INTERVALS_MS.fleet = 2000
    const calls: Record<string, number> = {}
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const name = (url.split('/').pop() ?? '').split('?')[0]
        calls[name] = (calls[name] ?? 0) + 1
        return Promise.resolve(jsonResponse(name === 'flights' ? { not: 'valid' } : []))
      }),
    )

    renderHook(() => {
      useFlights()
      useDrones()
      useOrders()
      useMissions()
    })
    await vi.advanceTimersByTimeAsync(0)
    expect(calls).toEqual({ flights: 1, drones: 1, orders: 1, missions: 1 })

    await vi.advanceTimersByTimeAsync(2000)

    expect(calls.flights).toBe(3) // at 0, 1 s and 2 s
    expect(calls.drones).toBe(2) // at 0 and 2 s
    expect(calls.orders).toBe(2)
    expect(calls.missions).toBe(2)
  })

  it('poll the live missions and the active orders, never the full history', async () => {
    POLL_INTERVALS_MS.fleet = 2000
    const urls = new Set<string>()
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        urls.add(url.replace(/^https?:\/\/[^/]+/, ''))
        return Promise.resolve(jsonResponse([]))
      }),
    )

    renderHook(() => {
      useOrders()
      useMissions()
    })
    await vi.advanceTimersByTimeAsync(6000)

    expect([...urls].sort()).toEqual([
      '/api/missions?status=ASSIGNED&status=IN_FLIGHT&status=EMERGENCY',
      '/api/orders?active=true',
    ])
  })
})
