import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { mapFocus } from './test/appMocks'
import { type Handler, okHubs, okDrones, stubBackend, hubMarkers } from './test/appHarness'
import { DRONE_RESPONSES } from './test/droneFixtures'
import { HUB_RESPONSES, jsonResponse } from './test/hubFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
import type { FocusRequest } from './features/map/focusTarget'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

describe('App map focus from the Operations lists (Feature 023)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    mapFocus.requests.length = 0
    mapFocus.last = null
  })

  const focusRequests = () => mapFocus.requests as FocusRequest[]
  const row = (name: RegExp) => screen.getByRole('button', { name })

  async function renderWithOperations(tab: string, drones: Handler = okDrones) {
    stubBackend(okHubs, drones)
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Operations' }))
    fireEvent.click(await screen.findByRole('tab', { name: new RegExp(`^${tab} \\(`) }))
  }

  it("focuses the map on a drone's coordinates, keeps the details open and the row selected", async () => {
    await renderWithOperations('Drones')
    const drone = DRONE_RESPONSES.find((candidate) => candidate.id === 'DRN-004')!

    fireEvent.click(row(/^DRN-004/))

    expect(focusRequests()).toHaveLength(1)
    expect(focusRequests()[0]).toMatchObject({
      kind: 'drone',
      id: 'DRN-004',
      position: [drone.longitude, drone.latitude],
    })
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-004' })).toBeVisible()
    expect(row(/^DRN-004/)).toHaveAttribute('aria-pressed', 'true')
  })

  it('focuses the map on a Hub and keeps its details open', async () => {
    await renderWithOperations('Hubs')
    const hub = HUB_RESPONSES.find((candidate) => candidate.name === 'Forum Gdańsk')!

    fireEvent.click(
      within(screen.getByRole('list', { name: 'Hubs' })).getByRole('button', {
        name: /Forum Gdańsk/,
      }),
    )

    expect(focusRequests()).toHaveLength(1)
    expect(focusRequests()[0]).toMatchObject({
      kind: 'hub',
      id: hub.id,
      position: [hub.longitude, hub.latitude],
    })
    expect(screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })).toBeVisible()
  })

  it('focuses the map on the delivery destination of an order, not on its Hub or drone', async () => {
    await renderWithOperations('Orders')
    const order = ORDER_RESPONSES.find((candidate) => candidate.id === 'ORD-006')!

    fireEvent.click(row(/^ORD-006/))

    expect(focusRequests()).toHaveLength(1)
    expect(focusRequests()[0]).toMatchObject({
      kind: 'order',
      id: 'ORD-006',
      position: [order.destination_longitude, order.destination_latitude],
    })
    expect(screen.getByRole('complementary', { name: 'Order details: ORD-006' })).toBeVisible()
  })

  it('flies again when the same row is clicked again, with a new command each time', async () => {
    await renderWithOperations('Drones')

    fireEvent.click(row(/^DRN-004/))
    fireEvent.click(row(/^DRN-004/))
    fireEvent.click(row(/^DRN-004/))

    const requests = focusRequests()
    expect(requests).toHaveLength(3)
    expect(new Set(requests.map((request) => request.seq)).size).toBe(3)
    expect(new Set(requests.map((request) => request.position.join(','))).size).toBe(1)
    expect(row(/^DRN-004/)).toHaveAttribute('aria-pressed', 'true') // the selection is unchanged
  })

  it('ends on the latest entity after two quick clicks', async () => {
    await renderWithOperations('Drones')

    fireEvent.click(row(/^DRN-001/))
    fireEvent.click(row(/^DRN-012/))

    const last = focusRequests().at(-1)!
    expect(last.id).toBe('DRN-012')
    expect(last.seq).toBeGreaterThan(focusRequests()[0].seq)
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-012' })).toBeVisible()
  })

  it('does not issue a new command on an ordinary re-render or an unrelated action', async () => {
    await renderWithOperations('Drones')
    fireEvent.click(row(/^DRN-004/))
    expect(focusRequests()).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Management' })) // a re-render of the app
    fireEvent.click(
      within(screen.getByRole('dialog', { name: 'Management' })).getByRole('button', {
        name: 'Close',
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))
    fireEvent.click(screen.getByRole('button', { name: 'Operations' }))

    expect(focusRequests()).toHaveLength(1)
  })

  it('does not move the camera when a marker on the map is clicked', async () => {
    await renderWithOperations('Drones')

    fireEvent.click(screen.getByRole('button', { name: 'Marker Forum Gdańsk' }))
    fireEvent.click(screen.getByRole('button', { name: 'Order marker ORD-003' }))

    expect(focusRequests()).toHaveLength(0)
    expect(screen.getByRole('complementary', { name: 'Order details: ORD-003' })).toBeVisible()
  })

  it('does not move the camera from the Management orders table', async () => {
    stubBackend()
    render(<App />)
    await waitFor(() => expect(hubMarkers()).toHaveLength(4))
    fireEvent.click(screen.getByRole('button', { name: 'Management' }))
    const dialog = screen.getByRole('dialog', { name: 'Management' })

    fireEvent.click(within(dialog).getAllByRole('button', { name: /ORD-002/ })[0])

    expect(focusRequests()).toHaveLength(0)
    expect(screen.getByRole('complementary', { name: 'Order details: ORD-002' })).toBeVisible()
  })

  it('leaves the camera alone and says so when the location is unusable, then recovers', async () => {
    const withBrokenLocation = () =>
      Promise.resolve(
        jsonResponse(
          DRONE_RESPONSES.map((drone) =>
            drone.id === 'DRN-001' ? { ...drone, longitude: 0, latitude: 0 } : drone,
          ),
        ),
      )
    await renderWithOperations('Drones', withBrokenLocation)

    fireEvent.click(row(/^DRN-001/))

    expect(focusRequests()).toHaveLength(0) // the camera was not moved
    const notice = screen.getByText('The location of DRN-001 is not available.')
    expect(notice.closest('[role="status"]')).not.toBeNull() // announced politely
    expect(screen.getByRole('complementary', { name: 'Drone details: DRN-001' })).toBeVisible()

    fireEvent.click(row(/^DRN-002/)) // a usable one works normally and clears the message

    expect(focusRequests()).toHaveLength(1)
    expect(focusRequests()[0].id).toBe('DRN-002')
    expect(screen.queryByText(/is not available/)).not.toBeInTheDocument()
  })

  it('is operable from the keyboard: a list row is a native button', async () => {
    await renderWithOperations('Orders')

    const button = row(/^ORD-006/)

    expect(button.tagName).toBe('BUTTON') // Enter and Space activate it, like a click
    button.focus()
    expect(button).toHaveFocus()
  })
})
