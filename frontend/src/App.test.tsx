import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { HUB_RESPONSES, jsonResponse } from './test/hubFixtures'
import type { Hub } from './types/hub'

// The real map needs WebGL. This stand-in renders one button per Hub it is given, so the tests
// can assert exactly which Hubs reach the map and how selection flows back.
vi.mock('./features/map/MapView', () => ({
  MapView: ({
    hubs = [],
    selectedHubId = null,
    onSelectHub,
  }: {
    hubs?: readonly Hub[]
    selectedHubId?: string | null
    onSelectHub?: (id: string) => void
  }) => (
    <div data-testid="map">
      {hubs.map((hub) => (
        <button
          key={hub.id}
          type="button"
          aria-pressed={hub.id === selectedHubId}
          onClick={() => onSelectHub?.(hub.id)}
        >
          {`Marker ${hub.name}`}
        </button>
      ))}
    </div>
  ),
}))

type HubsHandler = () => Promise<Response>

function stubBackend(hubsHandler: HubsHandler) {
  const hubsCalls = vi.fn(hubsHandler)
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      url.endsWith('/api/health') ? Promise.resolve(jsonResponse({ status: 'ok' })) : hubsCalls(),
    ),
  )
  return hubsCalls
}

const markers = () => screen.queryAllByRole('button', { name: /^Marker / })

describe('App hub loading', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a loading message and no markers while hubs are being fetched', () => {
    stubBackend(() => new Promise(() => {}))

    render(<App />)

    expect(screen.getByText('Loading hubs…')).toBeInTheDocument()
    expect(markers()).toHaveLength(0)
  })

  it('renders the four API hubs on the map and no banner', async () => {
    stubBackend(() => Promise.resolve(jsonResponse(HUB_RESPONSES)))

    render(<App />)

    expect(await screen.findByRole('button', { name: 'Marker Forum Gdańsk' })).toBeInTheDocument()
    expect(markers().map((m) => m.textContent)).toEqual([
      'Marker Centrum Handlowe Osowa',
      'Marker Centrum Riviera',
      'Marker Forum Gdańsk',
      'Marker Galeria Bałtycka',
    ])
    expect(screen.queryByText('Loading hubs…')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows server-provided details when a marker is selected and closes the panel', async () => {
    stubBackend(() => Promise.resolve(jsonResponse(HUB_RESPONSES)))

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Marker Forum Gdańsk' }))

    const panel = screen.getByRole('complementary', { name: 'Hub details: Forum Gdańsk' })
    expect(within(panel).getByText('Targ Sienny 7, Gdańsk')).toBeInTheDocument()
    expect(within(panel).getByText('Maximum drone capacity').nextElementSibling).toHaveTextContent(
      '50',
    )

    fireEvent.click(within(panel).getByRole('button', { name: 'Close hub details' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('shows an empty state without inventing markers', async () => {
    stubBackend(() => Promise.resolve(jsonResponse([])))

    render(<App />)

    expect(await screen.findByText('No hubs are available yet.')).toBeInTheDocument()
    expect(markers()).toHaveLength(0)
  })

  it('shows an error with Retry when the request fails, then recovers on retry', async () => {
    const hubsCalls = stubBackend(() => Promise.reject(new TypeError('Failed to fetch')))

    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Hub data is unavailable')
    expect(markers()).toHaveLength(0)
    expect(screen.getByTestId('map')).toBeInTheDocument()

    hubsCalls.mockImplementation(() => Promise.resolve(jsonResponse(HUB_RESPONSES)))
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByRole('button', { name: 'Marker Forum Gdańsk' })).toBeInTheDocument()
    expect(markers()).toHaveLength(4)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(hubsCalls).toHaveBeenCalledTimes(2)
  })

  it('treats malformed data as an error instead of showing partial markers', async () => {
    stubBackend(() => Promise.resolve(jsonResponse([{ ...HUB_RESPONSES[0], latitude: 'north' }])))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Hub data is unavailable')
    expect(markers()).toHaveLength(0)
  })

  it('treats a server error status as an error', async () => {
    stubBackend(() => Promise.resolve(jsonResponse({ detail: 'oops' }, 500)))

    render(<App />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(markers()).toHaveLength(0)
  })
})
