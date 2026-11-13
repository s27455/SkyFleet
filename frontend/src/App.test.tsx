import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { DRONE_RESPONSES } from './test/droneFixtures'
import { HUB_RESPONSES, jsonResponse } from './test/hubFixtures'
import {
  ASSIGNED_MISSION,
  EMERGENCY_FLIGHT,
  OUTBOUND_FLIGHT,
  flightsResponse,
} from './test/flightFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
import { POLL_INTERVALS_MS } from './features/data/polling'
import type { FlightVisual } from './features/flights/interpolation'
import type { Drone, DroneResponse } from './types/drone'
import type { Order } from './types/order'
import type { Hub } from './types/hub'

// The real map needs WebGL. This stand-in renders one button per Hub (exposing its docked count) and
// per drone it is given, so the tests can assert exactly what reaches the map and how selection
// flows back.
vi.mock('./features/map/MapView', () => ({
  MapView: ({
    hubs = [],
    selectedHubId = null,
    onSelectHub,
    drones = [],
    dockedCounts = new Map(),
    selectedDroneId = null,
    onSelectDrone,
    orders = [],
    selectedOrderId = null,
    onSelectOrder,
    flights = [],
  }: {
    hubs?: readonly Hub[]
    selectedHubId?: string | null
    onSelectHub?: (id: string) => void
    drones?: readonly Drone[]
    dockedCounts?: ReadonlyMap<string, number>
    selectedDroneId?: string | null
    onSelectDrone?: (id: string) => void
    orders?: readonly Order[]
    selectedOrderId?: string | null
    onSelectOrder?: (id: string) => void
    flights?: readonly FlightVisual[]
  }) => (
    <div
      data-testid="map"
      data-flight-drones={flights.map((flight) => flight.droneId).join(',')}
      data-flight-animate={flights.map((flight) => String(flight.animate)).join(',')}
    >
      {hubs.map((hub) => (
        <button
          key={hub.id}
          type="button"
          aria-pressed={hub.id === selectedHubId}
          data-docked-count={dockedCounts.get(hub.id) ?? 0}
          onClick={() => onSelectHub?.(hub.id)}
        >
          {`Marker ${hub.name}`}
        </button>
      ))}
      {drones.map((drone) => (
        <button
          key={drone.id}
          type="button"
          aria-pressed={drone.id === selectedDroneId}
          onClick={() => onSelectDrone?.(drone.id)}
        >
          {`Drone marker ${drone.id}`}
        </button>
      ))}
      {orders.map((order) => (
        <button
          key={order.id}
          type="button"
          aria-pressed={order.id === selectedOrderId}
          onClick={() => onSelectOrder?.(order.id)}
        >
          {`Order marker ${order.id}`}
        </button>
      ))}
    </div>
  ),
}))

// The 3D viewer needs WebGL; the inspector tests only care that it is mounted (and how often).
const viewerMounts = vi.hoisted(() => ({ count: 0 }))
vi.mock('./features/drone3d', async () => {
  const { useEffect } = await import('react')
  return {
    Drone3DViewer: () => {
      useEffect(() => {
        viewerMounts.count += 1
      }, [])
      return <div data-testid="viewer" />
    },
  }
})

type Handler = () => Promise<Response>

const okHubs: Handler = () => Promise.resolve(jsonResponse(HUB_RESPONSES))
const okDrones: Handler = () => Promise.resolve(jsonResponse(DRONE_RESPONSES))
const okOrders: Handler = () => Promise.resolve(jsonResponse(ORDER_RESPONSES))
const okFlights: Handler = () => Promise.resolve(jsonResponse(flightsResponse()))
const okMissions: Handler = () => Promise.resolve(jsonResponse([]))
const okStart: Handler = () =>
  Promise.resolve(jsonResponse({ ...ASSIGNED_MISSION, status: 'IN_FLIGHT' }))

interface Handlers {
  hubs?: Handler
  drones?: Handler
  orders?: Handler
  flights?: Handler
  missions?: Handler
  start?: Handler
}

function stubBackend(
  hubsHandler: Handler = okHubs,
  dronesHandler: Handler = okDrones,
  ordersHandler: Handler = okOrders,
  more: Pick<Handlers, 'flights' | 'missions' | 'start'> = {},
) {
  const hubsCalls = vi.fn(hubsHandler)
  const dronesCalls = vi.fn(dronesHandler)
  const ordersCalls = vi.fn(ordersHandler)
  const flightsCalls = vi.fn(more.flights ?? okFlights)
  const missionsCalls = vi.fn(more.missions ?? okMissions)
  const startCalls = vi.fn(more.start ?? okStart)
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
      if (url.endsWith('/start')) return startCalls()
      if (url.endsWith('/api/orders')) return ordersCalls()
      if (url.endsWith('/api/flights')) return flightsCalls()
      if (url.endsWith('/api/missions')) return missionsCalls()
      return url.endsWith('/api/drones') ? dronesCalls() : hubsCalls()
    }),
  )
  return { hubsCalls, dronesCalls, ordersCalls, flightsCalls, missionsCalls, startCalls }
}

const hubMarkers = () => screen.queryAllByRole('button', { name: /^Marker / })
const droneMarkers = () => screen.queryAllByRole('button', { name: /^Drone marker / })
const HUB_NAMES = ['Centrum Handlowe Osowa', 'Centrum Riviera', 'Forum Gdańsk', 'Galeria Bałtycka']
const dockedCount = (hubName: string) =>
  screen.getByRole('button', { name: `Marker ${hubName}` }).getAttribute('data-docked-count')
const panels = () => screen.queryAllByRole('complementary')

describe('App hub loading', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a loading message and no markers while hubs are being fetched', () => {
    stubBackend(() => new Promise(() => {}))

    render(<App />)

    expect(screen.getByText('Loading hubs…')).toBeInTheDocument()
    expect(hubMarkers()).toHaveLength(0)
  })

  it('renders the four API hubs on the map and no hub banner', async () => {
    stubBackend()

    render(<App />)

    expect(await screen.findByRole('button', { name: 'Marker Forum Gdańsk' })).toBeInTheDocument()
    expect(hubMarkers().map((m) => m.textContent)).toEqual([
      'Marker Centrum Handlowe Osowa',
      'Marker Centrum Riviera',
      'Marker Forum Gdańsk',
      'Marker Galeria Bałtycka',
    ])
    expect(screen.queryByText('Loading hubs…')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows server-provided details when a marker is selected and closes the panel', async () => {
    stubBackend()

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Marker Forum Gdańsk' }))

    const panel = screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })
    expect(within(panel).getByText('Targ Sienny 7, Gdańsk')).toBeInTheDocument()
    expect(within(panel).getByText('Maximum drone capacity').nextElementSibling).toHaveTextContent(
      '50',
    )

    fireEvent.click(within(panel).getByRole('button', { name: 'Close hub details' }))
    expect(panels()).toHaveLength(0)
  })

  it('shows an empty state without inventing hub markers', async () => {
    stubBackend(() => Promise.resolve(jsonResponse([])))

    render(<App />)

    expect(await screen.findByText('No hubs are available yet.')).toBeInTheDocument()
    expect(hubMarkers()).toHaveLength(0)
  })

  it('shows an error with Retry when the hub request fails, then recovers on retry', async () => {
    const { hubsCalls } = stubBackend(() => Promise.reject(new TypeError('Failed to fetch')))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Hub data is unavailable')
    expect(hubMarkers()).toHaveLength(0)
    expect(screen.getByTestId('map')).toBeInTheDocument()

    hubsCalls.mockImplementation(okHubs)
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading hubs' }))

    expect(await screen.findByRole('button', { name: 'Marker Forum Gdańsk' })).toBeInTheDocument()
    expect(hubMarkers()).toHaveLength(4)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(hubsCalls).toHaveBeenCalledTimes(2)
  })

  it('treats malformed hub data as an error instead of showing partial markers', async () => {
    stubBackend(() => Promise.resolve(jsonResponse([{ ...HUB_RESPONSES[0], latitude: 'north' }])))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Hub data is unavailable')
    expect(hubMarkers()).toHaveLength(0)
  })

  it('treats a hub server error status as an error', async () => {
    stubBackend(() => Promise.resolve(jsonResponse({ detail: 'oops' }, 500)))

    render(<App />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(hubMarkers()).toHaveLength(0)
  })
})

// Seeded drones all sit idle at a Hub. This variant sends DRN-002 on a flight, parks DRN-003 for
// maintenance in the open, and lets DRN-004 (home: Riviera) sit at Osowa instead.
const OSOWA = HUB_RESPONSES[0]
const AWAY = { longitude: 18.5, latitude: 54.45 }
const MIXED_DRONES: DroneResponse[] = DRONE_RESPONSES.map((drone) => {
  if (drone.id === 'DRN-002') return { ...drone, status: 'IN_FLIGHT', ...AWAY }
  if (drone.id === 'DRN-003') return { ...drone, status: 'MAINTENANCE', ...AWAY }
  if (drone.id === 'DRN-004') {
    return { ...drone, longitude: OSOWA.longitude, latitude: OSOWA.latitude }
  }
  return drone
})
const okMixed: Handler = () => Promise.resolve(jsonResponse(MIXED_DRONES))

describe('App drone loading', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a loading message and no drone markers while drones are being fetched', () => {
    stubBackend(okHubs, () => new Promise(() => {}))

    render(<App />)

    expect(screen.getByText('Loading drones…')).toBeInTheDocument()
    expect(droneMarkers()).toHaveLength(0)
  })

  it('docks the twelve idle drones at their Hubs: badges, no individual markers', async () => {
    stubBackend()

    render(<App />)

    await screen.findAllByRole('button', { name: /^Marker / })
    await waitFor(() => expect(dockedCount('Forum Gdańsk')).toBe('3'))
    expect(HUB_NAMES.map(dockedCount)).toEqual(['3', '3', '3', '3'])
    expect(droneMarkers()).toHaveLength(0)
    expect(screen.queryByText('Loading drones…')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('gives markers only to in-flight drones and drones away from every Hub', async () => {
    stubBackend(okHubs, okMixed)

    render(<App />)

    expect(await screen.findByRole('button', { name: 'Drone marker DRN-002' })).toBeInTheDocument()
    expect(droneMarkers().map((m) => m.textContent)).toEqual([
      'Drone marker DRN-002',
      'Drone marker DRN-003',
    ])
    // DRN-004 counts where it physically is (Osowa), not at its home Hub (Riviera).
    await waitFor(() => expect(HUB_NAMES.map(dockedCount)).toEqual(['2', '2', '3', '3']))
  })

  it('shows an empty state without inventing drone markers', async () => {
    stubBackend(okHubs, () => Promise.resolve(jsonResponse([])))

    render(<App />)

    expect(await screen.findByText('No drones are available yet.')).toBeInTheDocument()
    expect(droneMarkers()).toHaveLength(0)
    expect(HUB_NAMES.map(dockedCount)).toEqual(['0', '0', '0', '0'])
  })

  it('keeps the hubs when the drone request fails, and recovers on retry', async () => {
    const { dronesCalls } = stubBackend(okHubs, () => Promise.reject(new TypeError('offline')))

    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Drone data is unavailable')
    expect(await screen.findAllByRole('button', { name: /^Marker / })).toHaveLength(4)
    expect(dockedCount('Forum Gdańsk')).toBe('0')
    expect(screen.queryByText(/Hub data is unavailable/)).not.toBeInTheDocument()

    dronesCalls.mockImplementation(okDrones)
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading drones' }))

    await waitFor(() => expect(dockedCount('Forum Gdańsk')).toBe('3'))
    expect(hubMarkers()).toHaveLength(4)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(dronesCalls).toHaveBeenCalledTimes(2)
  })

  it('draws only in-flight drones while the Hubs are unavailable (no false "not at a Hub")', async () => {
    stubBackend(() => Promise.reject(new TypeError('offline')), okMixed)

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Hub data is unavailable')
    expect(await screen.findByRole('button', { name: 'Drone marker DRN-002' })).toBeInTheDocument()
    expect(droneMarkers().map((m) => m.textContent)).toEqual(['Drone marker DRN-002'])
    expect(hubMarkers()).toHaveLength(0)
  })

  it('draws no drone markers before the Hubs load, then docks them without flagging any', async () => {
    let resolveHubs!: (response: Response) => void
    stubBackend(() => new Promise((resolve) => (resolveHubs = resolve)), okDrones)

    render(<App />)
    await waitFor(() => expect(screen.queryByText('Loading drones…')).not.toBeInTheDocument())
    expect(droneMarkers()).toHaveLength(0) // not 12 "away" markers

    resolveHubs(jsonResponse(HUB_RESPONSES))
    await waitFor(() => expect(dockedCount('Forum Gdańsk')).toBe('3'))
    expect(droneMarkers()).toHaveLength(0)
  })

  it('treats malformed drone data (bad coordinates) as an error, with no bogus markers', async () => {
    stubBackend(okHubs, () =>
      Promise.resolve(jsonResponse([{ ...DRONE_RESPONSES[0], longitude: 999 }])),
    )

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Drone data is unavailable')
    expect(droneMarkers()).toHaveLength(0)
  })
})

describe('App selection', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  async function renderMixed() {
    stubBackend(okHubs, okMixed)
    render(<App />)
    await screen.findByRole('button', { name: 'Drone marker DRN-002' })
    await screen.findAllByRole('button', { name: /^Marker / })
    await waitFor(() => expect(dockedCount('Centrum Riviera')).toBe('2'))
  }

  it("lists a Hub's docked drones and opens a drone from the list", async () => {
    stubBackend()
    render(<App />)
    await waitFor(() => expect(dockedCount('Centrum Riviera')).toBe('3'))

    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Riviera' }))
    const hubPanel = screen.getByRole('complementary', { name: 'Hub details: Centrum Riviera' })
    expect(within(hubPanel).getByText('Drones at this Hub (3)')).toBeInTheDocument()
    expect(
      within(hubPanel)
        .getAllByRole('button', { name: /DRN-/ })
        .map((b) => b.textContent),
    ).toEqual(['DRN-004Idle · 100%', 'DRN-005Idle · 90%', 'DRN-006Idle · 80%'])

    fireEvent.click(within(hubPanel).getByRole('button', { name: /DRN-005/ }))

    expect(panels()).toHaveLength(1)
    const panel = screen.getByRole('complementary', { name: 'Drone details: DRN-005' })
    expect(within(panel).getByText('Assigned Hub').nextElementSibling).toHaveTextContent(
      'Centrum Riviera',
    )
    expect(within(panel).getByText('Battery').nextElementSibling).toHaveTextContent('90%')
    expect(within(panel).getByText('Status').nextElementSibling).toHaveTextContent('Idle')
    expect(within(panel).getByText('Maximum payload').nextElementSibling).toHaveTextContent('3 kg')
    expect(within(panel).getByText('SkyFleet SF-1 Courier')).toBeInTheDocument()
  })

  it('lists a drone under the Hub where it physically is, not its home Hub', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Handlowe Osowa' }))
    const osowa = screen.getByRole('complementary', { name: 'Hub details: Centrum Handlowe Osowa' })
    expect(within(osowa).getByRole('button', { name: /DRN-004/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Marker Centrum Riviera' }))
    const riviera = screen.getByRole('complementary', { name: 'Hub details: Centrum Riviera' })
    expect(within(riviera).queryByRole('button', { name: /DRN-004/ })).not.toBeInTheDocument()
    expect(within(riviera).getByText('Drones at this Hub (2)')).toBeInTheDocument()
  })

  it('says so when no drone is docked at a Hub', async () => {
    stubBackend(okHubs, () => Promise.resolve(jsonResponse([])))
    render(<App />)
    await screen.findByText('No drones are available yet.')

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))

    expect(screen.getByText('No drones are docked here.')).toBeInTheDocument()
  })

  it('replaces the Hub panel when a marker drone is selected', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))
    expect(panels()).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))

    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-002' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Marker Forum Gdańsk' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(screen.getByRole('button', { name: 'Drone marker DRN-002' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('replaces the drone panel when a Hub is selected', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))
    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))

    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Drone marker DRN-002' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('switches between two marker drones with a single panel', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))
    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-003' }))

    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-003' })).toBeVisible()
  })

  it('closes the drone panel on Escape and with the close button', async () => {
    await renderMixed()

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-002' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(panels()).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Drone marker DRN-003' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close drone details' }))
    expect(panels()).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Drone marker DRN-003' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })
})

const orderMarkers = () => screen.queryAllByRole('button', { name: /^Order marker / })
const ordersToggle = () => screen.getByRole('button', { name: /^Orders \(/ })

describe('App orders', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  async function renderLoaded(ordersHandler: Handler = okOrders) {
    stubBackend(okHubs, okDrones, ordersHandler)
    render(<App />)
    await screen.findByRole('button', { name: 'Order marker ORD-001' })
  }

  it('shows a loading message and no order markers while orders are being fetched', () => {
    stubBackend(okHubs, okDrones, () => new Promise(() => {}))

    render(<App />)

    expect(screen.getByText('Loading orders…')).toBeInTheDocument()
    expect(orderMarkers()).toHaveLength(0)
    expect(screen.queryByRole('button', { name: /^Orders \(/ })).not.toBeInTheDocument()
  })

  it('puts all ten orders on the map and keeps the orders list closed by default', async () => {
    await renderLoaded()

    expect(orderMarkers()).toHaveLength(10)
    expect(ordersToggle()).toHaveTextContent('Orders (10)')
    expect(ordersToggle()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: /ORD-001.*Ready for pickup/ })).toBeNull()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('opens and closes the list with the toggle', async () => {
    await renderLoaded()

    fireEvent.click(ordersToggle())
    expect(ordersToggle()).toHaveAttribute('aria-expanded', 'true')
    const rows = within(screen.getByRole('region', { name: 'Orders' })).getAllByRole('button', {
      name: /ORD-/,
    })
    expect(rows).toHaveLength(10)
    expect(rows[0]).toHaveTextContent('ORD-001')
    expect(rows[0]).toHaveTextContent('Ready for pickup · 0.8 kg')
    expect(rows[0]).toHaveTextContent('Galeria Bałtycka → ul. Grunwaldzka 82, Gdańsk')

    fireEvent.click(ordersToggle())
    expect(ordersToggle()).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens the order details from a list row and highlights its destination marker', async () => {
    await renderLoaded()

    fireEvent.click(ordersToggle())
    fireEvent.click(screen.getByRole('button', { name: /^ORD-006/ }))

    const panel = screen.getByRole('complementary', { name: 'Order details: ORD-006' })
    expect(within(panel).getByText('Origin Hub').nextElementSibling).toHaveTextContent(
      'Forum Gdańsk',
    )
    expect(within(panel).getByText('Package weight').nextElementSibling).toHaveTextContent('3 kg')
    expect(within(panel).getByText('Destination').nextElementSibling).toHaveTextContent(
      'ul. Podwale Staromiejskie 60, Gdańsk',
    )
    expect(within(panel).getByText('Destination position').nextElementSibling).toHaveTextContent(
      '54.355800, 18.645900',
    )
    expect(within(panel).getByText('Created').nextElementSibling).toHaveTextContent(
      '11 Nov 2026, 21:53 UTC',
    )
    expect(within(panel).getByText('Status').nextElementSibling).toHaveTextContent(
      'Ready for pickup',
    )
    expect(within(panel).queryByText(/drone/i)).toBeNull()
    expect(screen.getByRole('button', { name: /^ORD-006/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Order marker ORD-006' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: 'Order marker ORD-001' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('opens the same order when its destination marker is selected', async () => {
    await renderLoaded()

    fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-003' }))
    fireEvent.click(ordersToggle())

    expect(screen.getByRole('complementary', { name: 'Order details: ORD-003' })).toBeVisible()
    expect(screen.getByRole('button', { name: /^ORD-003/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows one details context at a time across Hubs, drones and orders', async () => {
    await renderLoaded()
    await screen.findAllByRole('button', { name: /^Marker / })

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))
    fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-004' }))
    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Order details: ORD-004' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Marker Forum Gdańsk' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))
    expect(panels()).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Order marker ORD-004' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-005' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close order details' }))
    expect(panels()).toHaveLength(0)
  })

  it('hides the list on narrow screens while a panel is open, keeping its open state', async () => {
    await renderLoaded()
    const section = () => screen.getByRole('region', { name: 'Orders', hidden: true })

    fireEvent.click(ordersToggle())
    expect(section()).not.toHaveClass('max-sm:hidden')

    fireEvent.click(screen.getByRole('button', { name: /^ORD-002/ }))
    expect(section()).toHaveClass('max-sm:hidden')
    expect(ordersToggle()).toHaveAttribute('aria-expanded', 'true')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(section()).not.toHaveClass('max-sm:hidden')
  })

  it('references the list from the toggle only while it is open', async () => {
    await renderLoaded()

    expect(ordersToggle()).not.toHaveAttribute('aria-controls')
    fireEvent.click(ordersToggle())
    const id = ordersToggle().getAttribute('aria-controls')
    expect(id).toBeTruthy()
    expect(document.getElementById(id!)).toBeInTheDocument()
  })

  it('closes the order details on Escape', async () => {
    await renderLoaded()

    fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-001' }))
    fireEvent.keyDown(window, { key: 'Escape' })

    expect(panels()).toHaveLength(0)
  })

  it('shows the origin Hub id while the Hub data is unavailable', async () => {
    stubBackend(() => Promise.reject(new TypeError('offline')), okDrones, okOrders)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))

    const panel = screen.getByRole('complementary', { name: 'Order details: ORD-001' })
    expect(within(panel).getByText('Origin Hub').nextElementSibling).toHaveTextContent(
      'hub-galeria-baltycka',
    )
  })

  it('shows an empty state without inventing order markers or a list', async () => {
    stubBackend(okHubs, okDrones, () => Promise.resolve(jsonResponse([])))

    render(<App />)

    expect(await screen.findByText('No orders are available yet.')).toBeInTheDocument()
    expect(orderMarkers()).toHaveLength(0)
    expect(screen.queryByRole('button', { name: /^Orders \(/ })).not.toBeInTheDocument()
  })

  it('keeps Hubs and drones when the order request fails, and recovers on retry', async () => {
    const stub = stubBackend(okHubs, okDrones, () => Promise.reject(new TypeError('offline')))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Order data is unavailable')
    expect(await screen.findAllByRole('button', { name: /^Marker / })).toHaveLength(4)
    await waitFor(() => expect(dockedCount('Forum Gdańsk')).toBe('3'))
    expect(orderMarkers()).toHaveLength(0)

    stub.ordersCalls.mockImplementation(okOrders)
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading orders' }))

    expect(await screen.findByRole('button', { name: 'Order marker ORD-001' })).toBeInTheDocument()
    expect(orderMarkers()).toHaveLength(10)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(stub.ordersCalls).toHaveBeenCalledTimes(2)
  })

  it('treats malformed order data as an error, with no bogus markers', async () => {
    stubBackend(okHubs, okDrones, () =>
      Promise.resolve(jsonResponse([{ ...ORDER_RESPONSES[0], destination_longitude: 999 }])),
    )

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Order data is unavailable')
    expect(orderMarkers()).toHaveLength(0)
  })
})

// --- live flights, emergencies and the temporary Start Mission control --------------------------

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
    fireEvent.click(await screen.findByRole('button', { name: /^Orders \(/ }))

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

describe('App Start Mission control', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  const assigned = () => Promise.resolve(jsonResponse([ASSIGNED_MISSION]))

  it('is offered in the order panel for an assigned mission, with its planned return Hub', async () => {
    stubBackend(okHubs, okDrones, okOrders, { missions: assigned })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))

    const control = await screen.findByRole('region', { name: 'Mission MIS-AAAA0001' })
    expect(control).toHaveTextContent('returns to Galeria Bałtycka')
    expect(control).toHaveTextContent('planned, not reserved')
    expect(
      within(control).getByRole('button', { name: 'Start mission MIS-AAAA0001' }),
    ).toBeEnabled()
  })

  it('is not offered for orders and drones without an assigned mission', async () => {
    stubBackend(okHubs, okDrones, okOrders, { missions: assigned })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-002' }))

    expect(screen.queryByRole('region', { name: /^Mission / })).not.toBeInTheDocument()
  })

  it('is offered in the drone panel, and the Hub list hints which drone has a mission', async () => {
    stubBackend(okHubs, okDrones, okOrders, { missions: assigned })

    render(<App />)
    await waitFor(() => expect(dockedCount('Galeria Bałtycka')).toBe('3'))
    fireEvent.click(screen.getByRole('button', { name: 'Marker Galeria Bałtycka' }))
    const hubPanel = screen.getByRole('complementary', { name: 'Hub details: Galeria Bałtycka' })
    const rows = within(hubPanel).getAllByRole('button', { name: /DRN-/ })
    expect(rows[0]).toHaveTextContent('mission assigned') // DRN-010
    expect(rows[1]).not.toHaveTextContent('mission assigned')

    fireEvent.click(within(hubPanel).getByRole('button', { name: /DRN-010/ }))

    expect(
      await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' }),
    ).toBeInTheDocument()
  })

  it('starts the mission through the backend and refreshes at once', async () => {
    const { startCalls, dronesCalls, ordersCalls, flightsCalls, missionsCalls } = stubBackend(
      okHubs,
      okDrones,
      okOrders,
      { missions: assigned },
    )

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))
    const before = [dronesCalls, ordersCalls, flightsCalls, missionsCalls].map(
      (calls) => calls.mock.calls.length,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' }))

    await waitFor(() => expect(startCalls).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(
        [dronesCalls, ordersCalls, flightsCalls, missionsCalls].map(
          (calls) => calls.mock.calls.length,
        ),
      ).toEqual(before.map((count) => count + 1)),
    )
  })

  it('disables the button while the start is in progress', async () => {
    let finish!: (response: Response) => void
    stubBackend(okHubs, okDrones, okOrders, {
      missions: assigned,
      start: () => new Promise<Response>((resolve) => (finish = resolve)),
    })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' }))

    const pending = await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' })
    await waitFor(() => expect(pending).toBeDisabled())
    expect(pending).toHaveTextContent('Starting…')
    finish(jsonResponse({ ...ASSIGNED_MISSION, status: 'IN_FLIGHT' }))
    // After a success it stays off (no second, refused click) until the mission leaves ASSIGNED.
    await waitFor(() => expect(pending).toHaveTextContent('Mission started'))
    expect(pending).toBeDisabled()
  })

  it('explains clearly when the simulation worker is not running', async () => {
    stubBackend(okHubs, okDrones, okOrders, {
      missions: assigned,
      start: () =>
        Promise.resolve(
          jsonResponse(
            { detail: { code: 'SIMULATION_WORKER_UNAVAILABLE', message: 'no heartbeat' } },
            503,
          ),
        ),
    })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('simulation worker is not running')
    expect(alert).toHaveTextContent('app.worker')
  })

  it('lists the backend reasons when the mission is no longer eligible', async () => {
    stubBackend(okHubs, okDrones, okOrders, {
      missions: assigned,
      start: () =>
        Promise.resolve(
          jsonResponse(
            {
              detail: {
                code: 'MISSION_NOT_ELIGIBLE',
                message: 'x',
                plan: {
                  reasons: [
                    { code: 'INSUFFICIENT_BATTERY', message: 'Drone battery is 10%.' },
                    { code: 'ORDER_NOT_READY', message: 'Order is AWAITING_HANDOVER.' },
                  ],
                },
              },
            },
            409,
          ),
        ),
    })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('no longer eligible')
    expect(alert).toHaveTextContent('Drone battery is 10%.')
    expect(alert).toHaveTextContent('Order is AWAITING_HANDOVER.')
  })

  it('hides the control and says why when the missions cannot be read', async () => {
    const { missionsCalls } = stubBackend(okHubs, okDrones, okOrders, {
      missions: () => Promise.reject(new TypeError('offline')),
    })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-001' }))

    expect(await screen.findByText(/Mission data is unavailable/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /^Mission / })).not.toBeInTheDocument()
    missionsCalls.mockImplementation(assigned)
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading missions' }))
    expect(
      await screen.findByRole('button', { name: 'Start mission MIS-AAAA0001' }),
    ).toBeInTheDocument()
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

describe('App management area', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens an overlay with Orders and Drones tabs and keeps the map mounted', async () => {
    stubBackend()
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))

    fireEvent.click(screen.getByRole('button', { name: 'Management' }))

    const dialog = screen.getByRole('dialog', { name: 'Management' })
    expect(within(dialog).getByRole('tab', { name: 'Orders' })).toBeInTheDocument()
    expect(within(dialog).getByText(`Orders (${ORDER_RESPONSES.length})`)).toBeInTheDocument()
    expect(hubMarkers()).toHaveLength(4)

    fireEvent.click(within(dialog).getByRole('tab', { name: 'Drones' }))
    expect(within(dialog).getByText(`Drones (${DRONE_RESPONSES.length})`)).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: 'Management' })).not.toBeInTheDocument()
  })

  it('shows the Order Simulation controls and refreshes the orders after Generate One Order', async () => {
    const { ordersCalls } = stubBackend()
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))
    fireEvent.click(screen.getByRole('button', { name: 'Management' }))
    const dialog = screen.getByRole('dialog', { name: 'Management' })

    const panel = await within(dialog).findByRole('region', { name: 'Order simulation' })
    expect(await within(panel).findByText('3 / 20')).toBeInTheDocument()
    const readsBefore = ordersCalls.mock.calls.length

    fireEvent.click(within(panel).getByRole('button', { name: 'Generate One Order' }))

    expect(await within(panel).findByText('Created order ORD-NEW00001.')).toBeInTheDocument()
    await waitFor(() => expect(ordersCalls.mock.calls.length).toBeGreaterThan(readsBefore))
    const generateCalls = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => String(url).endsWith('/api/orders/generate'))
    expect(generateCalls).toHaveLength(1)
  })
})

// DRN-002 flies mission MIS-AAAA0001 carrying order ORD-001; DRN-003 sits in maintenance.
const DRN002_FLIGHT = {
  ...OUTBOUND_FLIGHT,
  drone_id: 'DRN-002',
  position: [AWAY.longitude, AWAY.latitude] as [number, number],
}
const DRN002_MISSION = { ...ASSIGNED_MISSION, drone_id: 'DRN-002', status: 'IN_FLIGHT' }

describe('App drone inspector', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    viewerMounts.count = 0
  })
  afterEach(() => {
    POLL_INTERVALS_MS.fleet = null
    POLL_INTERVALS_MS.flights = null
  })

  async function openPanel(
    droneId: string,
    more: Pick<Handlers, 'flights' | 'missions'> = {},
    drones: Handler = okMixed,
  ) {
    const backend = stubBackend(okHubs, drones, okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([DRN002_FLIGHT]))),
      missions: () => Promise.resolve(jsonResponse([DRN002_MISSION])),
      ...more,
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: `Drone marker ${droneId}` }))
    return backend
  }

  const inspect = () => {
    const button = screen.getByRole('button', { name: 'Inspect Drone' })
    button.focus() // a real click focuses the button, which is where focus must come back to
    fireEvent.click(button)
  }
  const panel = (droneId: string) =>
    screen.getByRole('complementary', { name: `Drone details: ${droneId}` })

  it('opens from the drone panel with real flight, mission and parcel data', async () => {
    await openPanel('DRN-002')
    inspect()

    const dialog = screen.getByRole('dialog', { name: 'DRN-002' })
    expect(within(dialog).getByTestId('viewer')).toBeInTheDocument()
    await waitFor(() =>
      expect(within(dialog).getByText('Outbound with the parcel')).toBeInTheDocument(),
    )
    expect(within(dialog).getAllByText('MIS-AAAA0001').length).toBeGreaterThan(0)
    expect(
      within(dialog).getByText(`${ORDER_RESPONSES[0].package_weight_kg} kg`),
    ).toBeInTheDocument()
    // The drone panel stays mounted underneath and the map selection is untouched.
    expect(panel('DRN-002')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Drone marker DRN-002' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('shows labelled simulated telemetry next to the real data', async () => {
    await openPanel('DRN-002')
    inspect()

    const dialog = screen.getByRole('dialog', { name: 'DRN-002' })
    const telemetry = await within(dialog).findByRole('region', { name: 'Simulated telemetry' })
    expect(within(telemetry).getByText('Simulated')).toBeInTheDocument()
    await waitFor(() =>
      expect(within(telemetry).getByText('Flying, parcel on board')).toBeInTheDocument(),
    )
  })

  it('puts the header out of reach while it is open', async () => {
    await openPanel('DRN-002')
    inspect()

    expect(screen.getByRole('banner')).toHaveAttribute('inert')
  })

  it('closes on Escape without closing the drone panel, then restores focus and the header', async () => {
    await openPanel('DRN-002')
    inspect()

    // One Escape press reaches the document first and then the window.
    fireEvent.keyDown(document.body, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'DRN-002' })).toBeNull())
    expect(panel('DRN-002')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Drone marker DRN-002' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: 'Inspect Drone' })).toHaveFocus()
    expect(screen.getByRole('banner')).not.toHaveAttribute('inert')

    // With the inspector gone, Escape closes the panel as before.
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(panels()).toHaveLength(0)
  })

  it('closes with its button and keeps the same drone selected', async () => {
    await openPanel('DRN-003')
    inspect()
    fireEvent.click(screen.getByRole('button', { name: 'Close inspector' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(panel('DRN-003')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Drone marker DRN-003' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('says an idle drone has no flight, mission or parcel instead of inventing values', async () => {
    await openPanel('DRN-003')
    inspect()

    const dialog = screen.getByRole('dialog', { name: 'DRN-003' })
    await waitFor(() => expect(within(dialog).getByText('No active flight.')).toBeInTheDocument())
    expect(within(dialog).getByText('No active mission.')).toBeInTheDocument()
    expect(within(dialog).getByText('No parcel assigned.')).toBeInTheDocument()
  })

  it('shows mission data as unavailable when the missions cannot be read', async () => {
    await openPanel('DRN-003', {
      missions: () => Promise.resolve(jsonResponse({ detail: 'boom' }, 500)),
    })
    inspect()

    const dialog = screen.getByRole('dialog', { name: 'DRN-003' })
    await waitFor(() =>
      expect(within(dialog).getAllByText(/could not be read/).length).toBeGreaterThan(0),
    )
    expect(within(dialog).queryByText('No active mission.')).not.toBeInTheDocument()
  })

  it('updates from live polling without remounting the viewer', async () => {
    POLL_INTERVALS_MS.fleet = 30
    let battery = 90
    await openPanel('DRN-002', {}, () =>
      Promise.resolve(
        jsonResponse(
          MIXED_DRONES.map((drone) =>
            drone.id === 'DRN-002' ? { ...drone, battery_pct: (battery -= 1) } : drone,
          ),
        ),
      ),
    )
    inspect()
    const dialog = screen.getByRole('dialog', { name: 'DRN-002' })
    const shown = () =>
      within(dialog).getByRole('progressbar', { name: 'Battery' }).getAttribute('aria-valuenow')
    const first = shown()

    await waitFor(() => expect(shown()).not.toBe(first))

    expect(viewerMounts.count).toBe(1)
    expect(screen.getByRole('dialog', { name: 'DRN-002' })).toBe(dialog)
  })
})
