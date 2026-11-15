import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { DRONE_RESPONSES } from './droneFixtures'
import { HUB_RESPONSES, jsonResponse } from './hubFixtures'
import { ASSIGNED_MISSION, flightsResponse } from './flightFixtures'
import { ORDER_RESPONSES } from './orderFixtures'
import type { DroneResponse } from '../types/drone'

// Shared helpers for the App test files (App.*.test.tsx): a fake backend and common selectors.

export type Handler = () => Promise<Response>

export const okHubs: Handler = () => Promise.resolve(jsonResponse(HUB_RESPONSES))
export const okDrones: Handler = () => Promise.resolve(jsonResponse(DRONE_RESPONSES))
export const okOrders: Handler = () => Promise.resolve(jsonResponse(ORDER_RESPONSES))
export const okFlights: Handler = () => Promise.resolve(jsonResponse(flightsResponse()))
export const okMissions: Handler = () => Promise.resolve(jsonResponse([]))
export const okStart: Handler = () =>
  Promise.resolve(jsonResponse({ ...ASSIGNED_MISSION, status: 'IN_FLIGHT' }))

// Feature 026: a Copilot that is available and answers one fixed question.
export const COPILOT_ANSWER = {
  answer: 'Two drones are charging.',
  answer_cut_off: false,
  snapshot: {
    captured_at: '2026-11-15T14:03:07Z',
    data_status: 'complete',
    truncated: false,
    limitations: [],
    omitted: { drones: 0, hubs: 0, active_incidents: 0, recovered_alerts: 0 },
    named_drones: [],
  },
}

export interface Handlers {
  hubs?: Handler
  drones?: Handler
  orders?: Handler
  flights?: Handler
  missions?: Handler
  start?: Handler
}

export function stubBackend(
  hubsHandler: Handler = okHubs,
  dronesHandler: Handler = okDrones,
  ordersHandler: Handler = okOrders,
  more: Pick<Handlers, 'flights' | 'missions' | 'start'> = {},
) {
  const hubsCalls = vi.fn(hubsHandler)
  const dronesCalls = vi.fn(dronesHandler)
  const ordersCalls = vi.fn(ordersHandler)
  const allOrdersCalls = vi.fn(ordersHandler)
  const flightsCalls = vi.fn(more.flights ?? okFlights)
  const missionsCalls = vi.fn(more.missions ?? okMissions)
  const startCalls = vi.fn(more.start ?? okStart)
  const copilotStatusCalls = vi.fn()
  const copilotAskCalls = vi.fn()
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.endsWith('/api/health')) return Promise.resolve(jsonResponse({ status: 'ok' }))
      if (url.endsWith('/api/dispatch/auto/status')) {
        return Promise.resolve(
          jsonResponse({
            enabled: false,
            worker_running: true,
            last_check_at: null,
            last_outcome: null,
          }),
        )
      }
      if (url.endsWith('/api/orders/simulation/status')) {
        return Promise.resolve(
          jsonResponse({
            enabled: false,
            worker_running: true,
            last_check_at: null,
            last_outcome: null,
            outstanding_orders: 3,
            max_outstanding_orders: 20,
          }),
        )
      }
      if (url.endsWith('/api/orders/generate')) {
        return Promise.resolve(jsonResponse({ ...ORDER_RESPONSES[0], id: 'ORD-NEW00001' }, 201))
      }
      if (url.endsWith('/api/ai/copilot/status')) {
        copilotStatusCalls()
        return Promise.resolve(jsonResponse({ available: true }))
      }
      if (url.endsWith('/api/ai/copilot/ask')) {
        copilotAskCalls()
        return Promise.resolve(jsonResponse(COPILOT_ANSWER))
      }
      if (url.endsWith('/start')) return startCalls()
      if (url.endsWith('/api/orders?active=true')) return ordersCalls()
      if (url.endsWith('/api/orders')) return allOrdersCalls()
      if (url.endsWith('/api/flights')) return flightsCalls()
      if (url.endsWith('/api/missions')) return missionsCalls()
      if (url.endsWith('/api/incidents/lpr')) {
        return Promise.resolve(
          jsonResponse({ server_time: '2026-11-13T12:00:00Z', scenario: null }),
        )
      }
      if (url.endsWith('/api/incidents/rain-warning')) {
        return Promise.resolve(
          jsonResponse({ active: false, activated_at: null, cleared_at: null, origin: null }),
        )
      }
      if (url.endsWith('/api/incidents/random')) {
        return Promise.resolve(
          jsonResponse({
            enabled: false,
            worker_running: true,
            last_check_at: null,
            last_outcome: null,
          }),
        )
      }
      return url.endsWith('/api/drones') ? dronesCalls() : hubsCalls()
    }),
  )
  return {
    hubsCalls,
    dronesCalls,
    ordersCalls,
    allOrdersCalls,
    flightsCalls,
    missionsCalls,
    startCalls,
    copilotStatusCalls,
    copilotAskCalls,
  }
}

export const hubMarkers = () => screen.queryAllByRole('button', { name: /^Marker / })
export const droneMarkers = () => screen.queryAllByRole('button', { name: /^Drone marker / })
export const HUB_NAMES = [
  'Centrum Handlowe Osowa',
  'Centrum Riviera',
  'Forum Gdańsk',
  'Galeria Bałtycka',
]
export const dockedCount = (hubName: string) =>
  screen.getByRole('button', { name: `Marker ${hubName}` }).getAttribute('data-docked-count')
export const panels = () => screen.queryAllByRole('complementary')
export const OSOWA = HUB_RESPONSES[0]
export const AWAY = { longitude: 18.5, latitude: 54.45 }
export const MIXED_DRONES: DroneResponse[] = DRONE_RESPONSES.map((drone) => {
  if (drone.id === 'DRN-002') return { ...drone, status: 'IN_FLIGHT', ...AWAY }
  if (drone.id === 'DRN-003') return { ...drone, status: 'MAINTENANCE', ...AWAY }
  if (drone.id === 'DRN-004') {
    return { ...drone, longitude: OSOWA.longitude, latitude: OSOWA.latitude }
  }
  return drone
})
export const okMixed: Handler = () => Promise.resolve(jsonResponse(MIXED_DRONES))
