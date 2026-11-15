import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  type Handler,
  okHubs,
  okDrones,
  okOrders,
  stubBackend,
  dockedCount,
  panels,
} from './test/appHarness'
import { jsonResponse } from './test/hubFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
import { POLL_INTERVALS_MS } from './features/data/polling'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

const orderMarkers = () => screen.queryAllByRole('button', { name: /^Order marker / })
const ordersToggle = () => screen.getByRole('button', { name: 'Operations' })
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
    expect(screen.queryByRole('button', { name: /^ORD-/ })).not.toBeInTheDocument()
  })

  it('puts all ten orders on the map and keeps the orders list closed by default', async () => {
    await renderLoaded()

    expect(orderMarkers()).toHaveLength(10)
    expect(ordersToggle()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('tab')).toBeNull()
    expect(screen.queryByRole('button', { name: /ORD-001.*Ready for pickup/ })).toBeNull()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('opens and closes the list with the toggle', async () => {
    await renderLoaded()

    fireEvent.click(ordersToggle())
    expect(ordersToggle()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('tab', { name: 'Orders (10)' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    const rows = within(screen.getByRole('list', { name: 'Orders' })).getAllByRole('button', {
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

  it('drops a selected order, its marker and its list row when it leaves the active list', async () => {
    const previous = POLL_INTERVALS_MS.fleet
    POLL_INTERVALS_MS.fleet = 20 // must be set before the hooks mount
    try {
      const stub = stubBackend(okHubs, okDrones, okOrders)
      render(<App />)
      fireEvent.click(await screen.findByRole('button', { name: 'Order marker ORD-003' }))
      expect(screen.getByRole('complementary', { name: 'Order details: ORD-003' })).toBeVisible()

      // The backend's next answer no longer contains ORD-003 (its delivered window ended).
      stub.ordersCalls.mockImplementation(() =>
        Promise.resolve(jsonResponse(ORDER_RESPONSES.filter((order) => order.id !== 'ORD-003'))),
      )
      await waitFor(() => expect(orderMarkers()).toHaveLength(9))

      expect(screen.queryByRole('button', { name: 'Order marker ORD-003' })).toBeNull()
      expect(screen.queryByRole('complementary', { name: 'Order details: ORD-003' })).toBeNull()
      fireEvent.click(ordersToggle())
      expect(screen.getByRole('tab', { name: 'Orders (9)' })).toBeInTheDocument()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      // The other orders are still selectable afterwards.
      fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-004' }))
      expect(screen.getByRole('complementary', { name: 'Order details: ORD-004' })).toBeVisible()
    } finally {
      POLL_INTERVALS_MS.fleet = previous
    }
  })

  it('shows the delivery marker legend over the map', async () => {
    await renderLoaded()

    expect(screen.getByRole('region', { name: 'Delivery marker legend' })).toBeInTheDocument()
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
    const section = () => screen.getByRole('region', { name: 'Operations', hidden: true })

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
