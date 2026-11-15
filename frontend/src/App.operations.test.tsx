import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { okHubs, okOrders, stubBackend, hubMarkers } from './test/appHarness'
import { DRONE_RESPONSES } from './test/droneFixtures'
import { jsonResponse } from './test/hubFixtures'
import { EMERGENCY_FLIGHT, flightsResponse } from './test/flightFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
import { POLL_INTERVALS_MS } from './features/data/polling'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

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
    expect(
      within(dialog).getByText(`Active orders (${ORDER_RESPONSES.length})`),
    ).toBeInTheDocument()
    expect(hubMarkers()).toHaveLength(4)

    fireEvent.click(within(dialog).getByRole('tab', { name: 'Drones' }))
    expect(within(dialog).getByText(`Drones (${DRONE_RESPONSES.length})`)).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: 'Management' })).not.toBeInTheDocument()
  })

  it('shows only the 200 most recent orders in All, asked of the backend and never the whole history', async () => {
    const { allOrdersCalls, unexpectedCalls } = stubBackend()
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))
    fireEvent.click(screen.getByRole('button', { name: 'Management' }))
    const dialog = screen.getByRole('dialog', { name: 'Management' })

    fireEvent.click(within(dialog).getByRole('button', { name: 'All' }))

    await waitFor(() => expect(allOrdersCalls).toHaveBeenCalled())
    expect(
      vi
        .mocked(fetch)
        .mock.calls.map(([url]) => String(url))
        .some((url) => url.endsWith('/api/orders?limit=200')),
    ).toBe(true)
    expect(unexpectedCalls).toEqual([])
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

describe('App operations panel and header controls (Feature 021C)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  const maintenanceDrones = () =>
    DRONE_RESPONSES.map((drone) =>
      drone.id === 'DRN-010'
        ? { ...drone, status: 'MAINTENANCE' as const, longitude: 18.6012, latitude: 54.3821 }
        : drone,
    )
  const tabSelected = (name: RegExp | string) =>
    screen.getByRole('tab', { name }).getAttribute('aria-selected')

  it('puts Auto dispatch, Automatic orders and Scenarios in the header', async () => {
    stubBackend()
    render(<App />)

    const header = screen.getByRole('banner')
    expect(await within(header).findByRole('switch', { name: 'Auto dispatch' })).toBeInTheDocument()
    expect(await within(header).findByRole('switch', { name: 'Automatic orders' })).toBeVisible()
    expect(within(header).getByRole('button', { name: /Scenarios/ })).toBeInTheDocument()
  })

  it('moved the scenarios and the switch out of Management, keeping Generate One Order there', async () => {
    stubBackend()
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))
    fireEvent.click(screen.getByRole('button', { name: 'Management' }))
    const dialog = screen.getByRole('dialog', { name: 'Management' })

    expect(await within(dialog).findByRole('button', { name: 'Generate One Order' })).toBeVisible()
    expect(within(dialog).queryByRole('switch', { name: 'Automatic orders' })).toBeNull()
    expect(within(dialog).queryByRole('region', { name: 'Simulation events' })).toBeNull()
  })

  it('polls the order simulation state once for both the switch and Management', async () => {
    stubBackend()
    render(<App />)
    await screen.findByRole('switch', { name: 'Automatic orders' })
    fireEvent.click(screen.getByRole('button', { name: 'Management' }))
    await screen.findByRole('button', { name: 'Generate One Order' })

    const reads = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => String(url).endsWith('/api/orders/simulation/status'))
    expect(reads).toHaveLength(1)
  })

  it('follows a map selection with the tab, without opening the closed panel', async () => {
    stubBackend(okHubs, () => Promise.resolve(jsonResponse(maintenanceDrones())))
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))
    const toggle = () => screen.getByRole('button', { name: 'Operations' })

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))
    expect(toggle()).toHaveAttribute('aria-expanded', 'false') // not opened by the selection
    expect(screen.queryByRole('tab')).toBeNull()
    fireEvent.click(toggle())
    expect(tabSelected(/^Hubs/)).toBe('true')
    fireEvent.click(toggle())

    fireEvent.click(await screen.findByRole('button', { name: 'Drone marker DRN-010' }))
    fireEvent.click(toggle())
    expect(tabSelected(/^Drones/)).toBe('true')
    fireEvent.click(toggle())

    fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-004' }))
    fireEvent.click(toggle())
    expect(tabSelected(/^Orders/)).toBe('true')
  })

  it('keeps the selection and its details when the tab is switched by hand', async () => {
    stubBackend()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-004' }))
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    fireEvent.click(screen.getByRole('tab', { name: /^Drones/ }))
    fireEvent.click(screen.getByRole('tab', { name: /^Hubs/ }))
    fireEvent.click(screen.getByRole('tab', { name: 'Events' }))

    expect(screen.getByRole('complementary', { name: 'Order details: ORD-004' })).toBeVisible()
  })

  it('selects from the Drones and Hubs tabs and opens the usual details', async () => {
    stubBackend()
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    fireEvent.click(screen.getByRole('tab', { name: /^Drones/ }))
    fireEvent.click(screen.getByRole('button', { name: /^DRN-002/ }))
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-002' })).toBeVisible()

    fireEvent.click(screen.getByRole('tab', { name: /^Hubs/ }))
    fireEvent.click(
      within(screen.getByRole('tabpanel')).getByRole('button', { name: /Forum Gdańsk/ }),
    )
    expect(screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })).toBeVisible()
  })

  it('keeps an emergency alert visible outside the tabs and lists it in Events', async () => {
    stubBackend(okHubs, () => Promise.resolve(jsonResponse(maintenanceDrones())), okOrders, {
      flights: () => Promise.resolve(jsonResponse(flightsResponse([EMERGENCY_FLIGHT]))),
    })
    render(<App />)
    const alert = await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    fireEvent.click(screen.getByRole('tab', { name: /^Drones/ }))
    expect(alert).toBeVisible() // still over the map on another tab

    fireEvent.click(screen.getByRole('tab', { name: 'Events' }))
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Emergency: DRN-010')
    expect(screen.getByText(/Select a drone or an order/)).toBeInTheDocument()
  })

  it('shows the selected drone’s activity, not a global history, in Events', async () => {
    stubBackend()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-004' }))
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    fireEvent.click(screen.getByRole('tab', { name: 'Events' }))

    expect(
      await within(screen.getByRole('tabpanel')).findByRole('region', { name: 'Activity' }),
    ).toBeInTheDocument()
    const eventReads = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => String(url).includes('/api/events?'))
    expect(eventReads.map(([url]) => String(url))).toEqual(
      expect.arrayContaining([expect.stringContaining('/api/events?order_id=ORD-004')]),
    )
  })
})

describe('App Random incidents (Feature 021D-2)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  const statusReads = () =>
    vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/api/incidents/random'))

  it('shows the backend state of Random incidents in the Scenarios menu, OFF by default', async () => {
    stubBackend()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Scenarios/ }))

    const toggle = await screen.findByRole('switch', { name: 'Random incidents' })
    expect(toggle).toBeEnabled()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.queryByText('Available when incident scenarios are enabled.')).toBeNull()
  })

  it('polls the Random incidents status once, whether or not the menu is open', async () => {
    const previous = POLL_INTERVALS_MS.fleet
    POLL_INTERVALS_MS.fleet = 60_000 // no scheduled poll can fall inside this test
    try {
      stubBackend()
      render(<App />)
      await screen.findByRole('button', { name: /Scenarios/ })
      await waitFor(() => expect(statusReads()).toHaveLength(1))

      fireEvent.click(screen.getByRole('button', { name: /Scenarios/ }))
      await screen.findByRole('switch', { name: 'Random incidents' })
      fireEvent.click(screen.getByRole('button', { name: /Scenarios/ }))
      fireEvent.click(screen.getByRole('button', { name: /Scenarios/ }))

      expect(statusReads()).toHaveLength(1) // mounting or opening the menu adds no poll
    } finally {
      POLL_INTERVALS_MS.fleet = previous
    }
  })

  it('enables Random incidents through the API and then shows what the server reports', async () => {
    stubBackend()
    const backend = globalThis.fetch as unknown as (url: string) => Promise<Response>
    const server = { enabled: false }
    const status = () => ({
      enabled: server.enabled,
      worker_running: true,
      last_check_at: null,
      last_outcome: null,
    })
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/api/incidents/random/enable')) {
          server.enabled = true
          return Promise.resolve(jsonResponse(status()))
        }
        if (url.endsWith('/api/incidents/random')) return Promise.resolve(jsonResponse(status()))
        return backend(url)
      }),
    )
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /Scenarios/ }))

    fireEvent.click(await screen.findByRole('switch', { name: 'Random incidents' }))

    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Random incidents' })).toHaveAttribute(
        'aria-checked',
        'true',
      ),
    )
  })

  it('keeps the manual scenarios working next to the new switch', async () => {
    stubBackend()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Scenarios/ }))

    expect(await screen.findByRole('button', { name: /LPR helicopter/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /Activate Rain Warning/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /Drone failure/ })).toBeVisible()
  })
})
