import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  type Handler,
  okHubs,
  okDrones,
  okOrders,
  stubBackend,
  dockedCount,
} from './test/appHarness'
import { DRONE_RESPONSES } from './test/droneFixtures'
import { jsonResponse } from './test/hubFixtures'
import { EMERGENCY_FLIGHT, OUTBOUND_FLIGHT, flightsResponse } from './test/flightFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
import { POLL_INTERVALS_MS } from './features/data/polling'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

const IN_FLIGHT_DRONES = DRONE_RESPONSES.map((drone) =>
  drone.id === 'DRN-010'
    ? { ...drone, status: 'IN_FLIGHT' as const, longitude: 18.599, latitude: 54.38 }
    : drone,
)
const okFlyingDrones: Handler = () => Promise.resolve(jsonResponse(IN_FLIGHT_DRONES))
describe('App live flights', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a flying drone as its own marker with the flight in its panel', async () => {
    stubBackend(okHubs, okFlyingDrones, okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([OUTBOUND_FLIGHT]))),
    })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Drone marker DRN-010' }))

    await waitFor(() =>
      expect(screen.getByTestId('map')).toHaveAttribute('data-flight-drones', 'DRN-010'),
    )
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-animate', 'true')
    const panel = screen.getByRole('complementary', { name: 'Drone details: DRN-010' })
    const flight = within(within(panel).getByRole('region', { name: 'Flight' }))
    expect(flight.getByText('Outbound with the parcel')).toBeInTheDocument()
    expect(flight.getByRole('progressbar', { name: 'Flight progress' })).toHaveAttribute(
      'aria-valuenow',
      '25',
    )
    expect(flight.getByRole('progressbar', { name: 'Flight battery' })).toHaveAttribute(
      'aria-valuenow',
      '98',
    )
    expect(flight.getByText('MIS-AAAA0001')).toBeInTheDocument()
    expect(flight.getByText('Galeria Bałtycka')).toBeInTheDocument()
    expect(flight.getByText(/about \d+ s/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows no notice while all is well, even with the worker idle and no flights', async () => {
    stubBackend(okHubs, okDrones, okOrders, {
      flights: () =>
        Promise.resolve(
          jsonResponse(flightsResponse([], { worker_stale: true, worker_heartbeat_at: null })),
        ),
    })

    render(<App />)
    await screen.findAllByRole('button', { name: /^Marker / })

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/worker has stopped/)).not.toBeInTheDocument()
  })

  it('says so, and stops animating, when the worker stopped updating a flight', async () => {
    stubBackend(okHubs, okFlyingDrones, okOrders, {
      flights: () =>
        Promise.resolve(jsonResponse(flightsResponse([OUTBOUND_FLIGHT], { worker_stale: true }))),
    })

    render(<App />)

    expect(await screen.findByText(/worker has stopped updating flights/)).toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-animate', 'false')
  })

  it('does not animate when the user prefers reduced motion', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    stubBackend(okHubs, okFlyingDrones, okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([OUTBOUND_FLIGHT]))),
    })

    render(<App />)

    await waitFor(() =>
      expect(screen.getByTestId('map')).toHaveAttribute('data-flight-drones', 'DRN-010'),
    )
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-animate', 'false')
  })

  it('shows a simulated emergency as a persistent alert and keeps the drone visible', async () => {
    const parked = DRONE_RESPONSES.map((drone) =>
      drone.id === 'DRN-010'
        ? { ...drone, status: 'MAINTENANCE' as const, longitude: 18.6012, latitude: 54.3821 }
        : drone,
    )
    stubBackend(okHubs, () => Promise.resolve(jsonResponse(parked)), okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([EMERGENCY_FLIGHT]))),
    })

    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Simulated emergency: DRN-010 (MIS-AAAA0001)')
    expect(alert).not.toHaveTextContent('out of service') // compact until expanded
    fireEvent.click(within(alert).getByRole('button', { name: 'Show details for DRN-010' }))
    expect(alert).toHaveTextContent('every Hub it could reach was full')
    expect(alert).toHaveTextContent('out of service')
    expect(alert).toHaveTextContent('already delivered')
    // The drone in MAINTENANCE is a marker of its own and is not counted at the Hub.
    expect(await screen.findByRole('button', { name: 'Drone marker DRN-010' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Marker Galeria Bałtycka' })).toHaveAttribute(
      'data-docked-count',
      '2',
    )
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-drones', '') // not animated
    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-010' }))
    const panel = screen.getByRole('complementary', { name: 'Drone details: DRN-010' })
    expect(within(panel).getByText('Emergency')).toBeInTheDocument()
    expect(within(panel).getByText(/not a computed safe landing site/)).toBeInTheDocument()
  })

  it('keeps the map usable and offers a retry when the flights cannot be read', async () => {
    const { flightsCalls } = stubBackend(okHubs, okDrones, okOrders, {
      flights: () => Promise.reject(new TypeError('offline')),
    })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Live flight data is unavailable')
    expect(await screen.findAllByRole('button', { name: /^Marker / })).toHaveLength(4)
    flightsCalls.mockImplementation(() => Promise.resolve(jsonResponse(flightsResponse([]))))
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading flights' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('treats malformed flight data as an error instead of drawing bogus flights', async () => {
    stubBackend(okHubs, okFlyingDrones, okOrders, {
      flights: () =>
        Promise.resolve(
          jsonResponse(flightsResponse([{ ...OUTBOUND_FLIGHT, phase: 'WARP' as never }])),
        ),
    })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Live flight data is unavailable')
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-drones', '')
  })

  it('shows the new order statuses', async () => {
    const orders = ORDER_RESPONSES.map((order) =>
      order.id === 'ORD-001'
        ? { ...order, status: 'OUT_FOR_DELIVERY' as const }
        : order.id === 'ORD-002'
          ? { ...order, status: 'DELIVERED' as const }
          : order,
    )
    stubBackend(okHubs, okDrones, () => Promise.resolve(jsonResponse(orders)))

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Operations' }))

    expect(screen.getByRole('button', { name: /^ORD-001/ })).toHaveTextContent('Out for delivery')
    expect(screen.getByRole('button', { name: /^ORD-002/ })).toHaveTextContent('Delivered')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('counts a drone in MAINTENANCE at no Hub, as the backend does', async () => {
    const serviced = DRONE_RESPONSES.map((drone) =>
      drone.id === 'DRN-010' ? { ...drone, status: 'MAINTENANCE' as const } : drone,
    )
    stubBackend(okHubs, () => Promise.resolve(jsonResponse(serviced)))

    render(<App />)

    await waitFor(() => expect(dockedCount('Galeria Bałtycka')).toBe('2'))
    expect(await screen.findByRole('button', { name: 'Drone marker DRN-010' })).toBeInTheDocument()
  })
})

describe('App notices that need polling', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    POLL_INTERVALS_MS.flights = 30
    POLL_INTERVALS_MS.fleet = 30
  })
  afterEach(() => {
    POLL_INTERVALS_MS.flights = null
    POLL_INTERVALS_MS.fleet = null
  })

  it('says so when drone or order data could not be refreshed, and keeps showing the old data', async () => {
    let drones = 0
    stubBackend(
      okHubs,
      () => (++drones === 1 ? okDrones() : Promise.reject(new TypeError('offline'))),
      okOrders,
    )

    render(<App />)

    expect(
      await screen.findByText(/Drone or order data could not be refreshed/),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh fleet data' })).toBeInTheDocument()
    expect(dockedCount('Forum Gdańsk')).toBe('3') // the last known data is still there
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the last flight, stops it gliding and offers a refresh when the flights cannot be read', async () => {
    let flights = 0
    stubBackend(okHubs, okFlyingDrones, okOrders, {
      flights: () =>
        ++flights === 1
          ? Promise.resolve(jsonResponse(flightsResponse([OUTBOUND_FLIGHT])))
          : Promise.reject(new TypeError('offline')),
    })

    render(<App />)

    expect(await screen.findByText(/Live flight data could not be refreshed/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh flights' })).toBeInTheDocument()
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-drones', 'DRN-010')
    expect(screen.getByTestId('map')).toHaveAttribute('data-flight-animate', 'false') // matches the notice
  })

  it('reads drones, orders and missions at once when the set of flying missions changes', async () => {
    const { dronesCalls, ordersCalls, missionsCalls } = stubBackend(
      okHubs,
      okFlyingDrones,
      okOrders,
      {
        flights: () => Promise.resolve(jsonResponse(flightsResponse([OUTBOUND_FLIGHT]))),
      },
    )
    POLL_INTERVALS_MS.flights = null // no polling: only the change of flights can trigger a read
    POLL_INTERVALS_MS.fleet = null

    render(<App />)

    await waitFor(() => expect(dronesCalls.mock.calls.length).toBeGreaterThanOrEqual(2))
    expect(ordersCalls.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(missionsCalls.mock.calls.length).toBeGreaterThanOrEqual(2)
  })
})
