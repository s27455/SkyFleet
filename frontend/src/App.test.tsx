import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { DRONE_RESPONSES } from './test/droneFixtures'
import { HUB_RESPONSES, jsonResponse } from './test/hubFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
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
  }) => (
    <div data-testid="map">
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

type Handler = () => Promise<Response>

const okHubs: Handler = () => Promise.resolve(jsonResponse(HUB_RESPONSES))
const okDrones: Handler = () => Promise.resolve(jsonResponse(DRONE_RESPONSES))
const okOrders: Handler = () => Promise.resolve(jsonResponse(ORDER_RESPONSES))

function stubBackend(
  hubsHandler: Handler = okHubs,
  dronesHandler: Handler = okDrones,
  ordersHandler: Handler = okOrders,
) {
  const hubsCalls = vi.fn(hubsHandler)
  const dronesCalls = vi.fn(dronesHandler)
  const ordersCalls = vi.fn(ordersHandler)
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.endsWith('/api/health')) return Promise.resolve(jsonResponse({ status: 'ok' }))
      if (url.endsWith('/api/orders')) return ordersCalls()
      return url.endsWith('/api/drones') ? dronesCalls() : hubsCalls()
    }),
  )
  return { hubsCalls, dronesCalls, ordersCalls }
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
