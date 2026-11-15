import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { okHubs, okDrones, okOrders, stubBackend, dockedCount } from './test/appHarness'
import { jsonResponse } from './test/hubFixtures'
import { ASSIGNED_MISSION } from './test/flightFixtures'

vi.mock('./features/map/MapView', async () => ({
  MapView: (await import('./test/appMocks')).MapViewStub,
}))
vi.mock('./features/drone3d', async () => ({
  Drone3DViewer: (await import('./test/appMocks')).Drone3DViewerStub,
}))

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
