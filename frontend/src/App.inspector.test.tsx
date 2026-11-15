import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { viewerMounts } from './test/appMocks'
import {
  type Handler,
  okHubs,
  okOrders,
  type Handlers,
  stubBackend,
  panels,
  AWAY,
  MIXED_DRONES,
  okMixed,
} from './test/appHarness'
import { jsonResponse } from './test/hubFixtures'
import { ASSIGNED_MISSION, OUTBOUND_FLIGHT, flightsResponse } from './test/flightFixtures'
import { ORDER_RESPONSES } from './test/orderFixtures'
import { POLL_INTERVALS_MS } from './features/data/polling'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

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
