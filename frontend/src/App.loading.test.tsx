import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  okHubs,
  okDrones,
  stubBackend,
  hubMarkers,
  droneMarkers,
  HUB_NAMES,
  dockedCount,
  panels,
  okMixed,
} from './test/appHarness'
import { DRONE_RESPONSES } from './test/droneFixtures'
import { HUB_RESPONSES, jsonResponse } from './test/hubFixtures'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

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

  it('shows the rain warning banner when the backend reports it active', async () => {
    stubBackend()
    const backend = globalThis.fetch as unknown as (url: string) => Promise<Response>
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.endsWith('/api/incidents/rain-warning')
          ? Promise.resolve(
              jsonResponse({
                active: true,
                activated_at: '2026-11-14T10:00:00Z',
                cleared_at: null,
                origin: 'MANUAL',
              }),
            )
          : backend(url),
      ),
    )

    render(<App />)

    expect(await screen.findByRole('status', { name: 'Rain warning' })).toHaveTextContent(
      'New takeoffs suspended',
    )
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
