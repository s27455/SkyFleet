import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { POLL_INTERVALS_MS } from './features/data/polling'
import { LIVE_MISSIONS_QUERY, okDrones, okHubs, okOrders, stubBackend } from './test/appHarness'
import { EMERGENCY_FLIGHT, flightsResponse } from './test/flightFixtures'
import type { FlightResponse } from './types/flight'
import { jsonResponse } from './test/hubFixtures'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

const ACKNOWLEDGED_AT = '2026-11-12T10:06:00Z'
const OTHER_EMERGENCY: FlightResponse = {
  ...EMERGENCY_FLIGHT,
  mission_id: 'MIS-ACK00002',
  drone_id: 'DRN-011',
  emergency: {
    reason: 'DRONE_FAILURE',
    at: '2026-11-12T10:00:09Z',
    position: [18.6012, 54.3821],
    acknowledged_at: ACKNOWLEDGED_AT,
  },
}

/** Answers the acknowledge request with `handler` and everything else like the normal backend. */
function stubAcknowledge(handler: () => Promise<Response>) {
  const backend = vi.mocked(fetch)
  const base = backend.getMockImplementation() as (url: string) => Promise<Response>
  const calls = vi.fn(handler)
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => (url.includes('/acknowledge') ? calls() : base(url))),
  )
  return calls
}

const openEvents = () => {
  fireEvent.click(screen.getByRole('button', { name: 'Operations' }))
  fireEvent.click(screen.getByRole('tab', { name: 'Events' }))
}
const eventsNotice = (drone: string) => screen.queryByText(new RegExp(`^Emergency: ${drone} `))
const acknowledgeButton = (drone: string) =>
  screen.queryByRole('button', { name: `Acknowledge emergency for ${drone}` })

describe('App Events tab and emergency acknowledgement', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })
  afterEach(() => {
    POLL_INTERVALS_MS.flights = null
    POLL_INTERVALS_MS.fleet = null
  })

  it('lists an unacknowledged emergency and leaves out one the server reports acknowledged', async () => {
    stubBackend(okHubs, okDrones, okOrders, {
      flights: () =>
        Promise.resolve(jsonResponse(flightsResponse([EMERGENCY_FLIGHT, OTHER_EMERGENCY]))),
    })

    render(<App />)
    await screen.findByRole('button', { name: 'Acknowledge emergency for DRN-010' })
    openEvents()

    expect(eventsNotice('DRN-010')).toBeInTheDocument()
    expect(eventsNotice('DRN-011')).not.toBeInTheDocument()
  })

  it('removes the alert from the overlay and the Events tab once the acknowledgement succeeds', async () => {
    stubBackend(okHubs, okDrones, okOrders, {
      // A server that keeps answering "not acknowledged" (an old answer, or a slow database).
      flights: () => Promise.resolve(jsonResponse(flightsResponse([EMERGENCY_FLIGHT]))),
    })
    const acknowledge = stubAcknowledge(() =>
      Promise.resolve(
        jsonResponse({ mission_id: 'MIS-AAAA0001', acknowledged_at: ACKNOWLEDGED_AT }),
      ),
    )
    render(<App />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Acknowledge emergency for DRN-010' }),
    )
    openEvents()

    await waitFor(() => expect(acknowledgeButton('DRN-010')).not.toBeInTheDocument())
    expect(acknowledge).toHaveBeenCalledTimes(1)
    expect(eventsNotice('DRN-010')).not.toBeInTheDocument()
    expect(screen.getByText('No active alerts.')).toBeInTheDocument()
  })

  it('does not bring an acknowledged alert back when later polls still say "not acknowledged"', async () => {
    const { flightsCalls } = stubBackend(okHubs, okDrones, okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([EMERGENCY_FLIGHT]))),
    })
    stubAcknowledge(() =>
      Promise.resolve(
        jsonResponse({ mission_id: 'MIS-AAAA0001', acknowledged_at: ACKNOWLEDGED_AT }),
      ),
    )
    POLL_INTERVALS_MS.flights = 20
    render(<App />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Acknowledge emergency for DRN-010' }),
    )
    openEvents()
    await waitFor(() => expect(eventsNotice('DRN-010')).not.toBeInTheDocument())

    const readsAtAcknowledgement = flightsCalls.mock.calls.length
    await waitFor(() =>
      expect(flightsCalls.mock.calls.length).toBeGreaterThanOrEqual(readsAtAcknowledgement + 3),
    )

    expect(eventsNotice('DRN-010')).not.toBeInTheDocument()
    expect(acknowledgeButton('DRN-010')).not.toBeInTheDocument()
  })

  it('keeps the alert in both places and shows an error when the acknowledgement fails', async () => {
    stubBackend(okHubs, okDrones, okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([EMERGENCY_FLIGHT]))),
    })
    stubAcknowledge(() =>
      Promise.resolve(jsonResponse({ detail: { message: 'Database unavailable.' } }, 500)),
    )
    render(<App />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Acknowledge emergency for DRN-010' }),
    )
    openEvents()

    await waitFor(() =>
      expect(
        screen
          .getAllByRole('alert')
          .some((alert) => /Could not acknowledge this alert/.test(alert.textContent ?? '')),
      ).toBe(true),
    )
    expect(acknowledgeButton('DRN-010')).toBeEnabled() // it can be tried again
    expect(eventsNotice('DRN-010')).toBeInTheDocument()
  })

  it('never asks for the unbounded mission or order lists', async () => {
    const { unexpectedCalls, missionsCalls } = stubBackend()
    render(<App />)
    await screen.findByRole('button', { name: 'Marker Galeria Bałtycka' })

    expect(missionsCalls).toHaveBeenCalled()
    expect(unexpectedCalls).toEqual([])
    const urls = vi.mocked(fetch).mock.calls.map(([url]) => String(url))
    expect(urls.some((url) => url.endsWith(LIVE_MISSIONS_QUERY))).toBe(true)
  })
})
