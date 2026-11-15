import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { ORDER_RESPONSES } from '../../test/orderFixtures'
import type { Order, OrderStatus } from '../../types/order'
import type { RandomIncidentsStatus } from '../../types/randomIncidents'
import type { PolledResource } from '../data/usePolledResource'
import { SimulationEventsPanel } from './SimulationEventsPanel'

afterEach(() => vi.unstubAllGlobals())

const order = (status: OrderStatus): Order => ({
  id: 'ORD-001',
  originHubId: 'hub-galeria-baltycka',
  destinationAddress: 'ul. Grunwaldzka 82, Gdańsk',
  coordinates: [18.5972, 54.3768],
  packageWeightKg: 0.8,
  status,
  deliveredAt: null,
  cancelledAt: null,
  deliveryFailedAt: null,
  createdAt: '2026-11-11T21:53:08Z',
  updatedAt: '2026-11-11T21:53:08Z',
})

const OFF_STATUS: RandomIncidentsStatus = {
  enabled: false,
  workerRunning: true,
  lastCheckAt: null,
  lastOutcome: null,
}

function readyResource(data: RandomIncidentsStatus): PolledResource<RandomIncidentsStatus> {
  return {
    state: { status: 'ready', data },
    stale: false,
    receivedAt: null,
    retry: vi.fn(),
    refresh: vi.fn(),
  }
}

const cancelButton = () => screen.getByRole('button', { name: /Cancel order/ })
const confirmation = () => screen.getByRole('group', { name: 'Confirm cancellation' })

describe('SimulationEventsPanel', () => {
  it('has an enabled LPR helicopter control and no placeholder left', () => {
    render(<SimulationEventsPanel />)

    const button = screen.getByRole('button', { name: /LPR helicopter/ })
    expect(button).toBeEnabled()
    expect(button).toHaveTextContent('Cross the area')
    expect(screen.queryByText(/Coming in/)).not.toBeInTheDocument()
  })

  it('shows no Random incidents switch without the shared status (manual scenarios only)', () => {
    render(<SimulationEventsPanel />)

    expect(screen.queryByRole('switch', { name: 'Random incidents' })).toBeNull()
    expect(screen.queryByText('Available when incident scenarios are enabled.')).toBeNull()
  })

  it('shows the real Random incidents switch from the shared status', () => {
    render(<SimulationEventsPanel randomIncidents={readyResource(OFF_STATUS)} />)

    const toggle = screen.getByRole('switch', { name: 'Random incidents' })
    expect(toggle).toBeEnabled() // no longer the disabled placeholder
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.queryByText('Available when incident scenarios are enabled.')).toBeNull()
  })

  it('keeps Cancel order disabled, and calls nothing, without a selected order', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<SimulationEventsPanel />)

    expect(cancelButton()).toBeDisabled()
    expect(cancelButton()).toHaveTextContent('Select an order')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each<OrderStatus>(['DELIVERED', 'CANCELLED'])(
    'keeps Cancel order disabled for a %s order',
    (status) => {
      render(<SimulationEventsPanel selectedOrder={order(status)} />)

      expect(cancelButton()).toBeDisabled()
      expect(cancelButton()).toHaveTextContent('Not available')
    },
  )

  it.each<OrderStatus>(['READY_FOR_PICKUP', 'OUT_FOR_DELIVERY'])(
    'enables Cancel order for a %s order, but only asks for confirmation on click',
    (status) => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)
      render(<SimulationEventsPanel selectedOrder={order(status)} />)

      fireEvent.click(cancelButton())

      expect(confirmation()).toHaveTextContent('permanent')
      expect(fetchMock).not.toHaveBeenCalled() // nothing is sent before the confirmation
    },
  )

  it('explains the recall when the parcel is in flight, and not otherwise', () => {
    const { rerender } = render(<SimulationEventsPanel selectedOrder={order('OUT_FOR_DELIVERY')} />)
    fireEvent.click(cancelButton())
    expect(confirmation()).toHaveTextContent('return to the nearest reachable Hub')

    rerender(<SimulationEventsPanel selectedOrder={order('READY_FOR_PICKUP')} />)
    fireEvent.click(cancelButton())
    expect(confirmation()).not.toHaveTextContent('reachable Hub')
  })

  it('keeps Drone failure disabled, and calls nothing, while no drone is flying', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<SimulationEventsPanel />)

    const button = screen.getByRole('button', { name: /Drone failure/ })
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('No drone is flying')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fails one drone on click, shows pending and the result, and refreshes the views', async () => {
    let release: (response: Response) => void = () => {}
    const fetchMock = vi.fn(
      (_url: string, _init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onDroneFailed = vi.fn()
    render(<SimulationEventsPanel canFailDrone onDroneFailed={onDroneFailed} />)

    const button = screen.getByRole('button', { name: /Drone failure/ })
    expect(button).toBeEnabled()
    fireEvent.click(button)
    fireEvent.click(button) // a second click while pending must not send a second request

    expect(await screen.findByText('Triggering…')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/drone-failure$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')

    release(
      jsonResponse({
        drone_id: 'DRN-010',
        mission_id: 'MIS-AAAA0001',
        order_id: 'ORD-001',
        stage: 'BEFORE_DELIVERY',
        landing_position: [18.6, 54.38],
      }),
    )

    expect(
      await screen.findByText('Drone DRN-010 failed: emergency landing in progress.'),
    ).toBeInTheDocument()
    expect(onDroneFailed).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows "no eligible target" as information, not as an error or a success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            { detail: { code: 'NO_ELIGIBLE_TARGET', message: 'No drone is flying' } },
            409,
          ),
        ),
      ),
    )
    const onDroneFailed = vi.fn()
    render(<SimulationEventsPanel canFailDrone onDroneFailed={onDroneFailed} />)

    fireEvent.click(screen.getByRole('button', { name: /Drone failure/ }))

    expect(
      await screen.findByText('No drone is flying a mission that a failure could interrupt.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/failed: emergency landing/)).not.toBeInTheDocument()
    await waitFor(() => expect(onDroneFailed).toHaveBeenCalledTimes(1))
  })

  it('shows any other failure of the request as an error, never as a success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    render(<SimulationEventsPanel canFailDrone />)

    fireEvent.click(screen.getByRole('button', { name: /Drone failure/ }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText(/failed: emergency landing/)).not.toBeInTheDocument()
  })

  it('keeps Recipient unavailable disabled, and calls nothing, while no delivery is on its way', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<SimulationEventsPanel />)

    const button = screen.getByRole('button', { name: /Recipient unavailable/ })
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('No delivery on its way')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('marks one delivery on click, says the failure is pending and refreshes the views', async () => {
    let release: (response: Response) => void = () => {}
    const fetchMock = vi.fn(
      (_url: string, _init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onRecipientMarked = vi.fn()
    render(<SimulationEventsPanel canMarkRecipient onRecipientMarked={onRecipientMarked} />)

    const button = screen.getByRole('button', { name: /Recipient unavailable/ })
    expect(button).toBeEnabled()
    fireEvent.click(button)
    fireEvent.click(button) // a second click while pending must not send a second request

    expect(await screen.findByText('Triggering…')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/recipient-unavailable$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')

    release(
      jsonResponse({
        drone_id: 'DRN-010',
        mission_id: 'MIS-AAAA0001',
        order_id: 'ORD-001',
        attempt_at: '2026-11-13T12:00:20Z',
      }),
    )

    const note = await screen.findByText(/Recipient unavailable reported for ORD-001/)
    expect(note).toHaveTextContent('The delivery fails when the drone reaches the destination.')
    expect(note).not.toHaveTextContent('failed:') // nothing has failed yet
    expect(onRecipientMarked).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows "no eligible target" for Recipient unavailable as information, not as an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'NO_ELIGIBLE_TARGET', message: 'Nothing' } }, 409),
        ),
      ),
    )
    const onRecipientMarked = vi.fn()
    render(<SimulationEventsPanel canMarkRecipient onRecipientMarked={onRecipientMarked} />)

    fireEvent.click(screen.getByRole('button', { name: /Recipient unavailable/ }))

    expect(
      await screen.findByText(/No drone is on its way to a delivery that could still fail/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/reported for/)).not.toBeInTheDocument()
    await waitFor(() => expect(onRecipientMarked).toHaveBeenCalledTimes(1))
  })

  it('shows any other failure of the Recipient unavailable request as an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    render(<SimulationEventsPanel canMarkRecipient />)

    fireEvent.click(screen.getByRole('button', { name: /Recipient unavailable/ }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText(/reported for/)).not.toBeInTheDocument()
  })

  it('starts the helicopter on click, shows pending and the result, and refreshes the views', async () => {
    let release: (response: Response) => void = () => {}
    const fetchMock = vi.fn(
      (_url: string, _init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onLprTriggered = vi.fn()
    render(<SimulationEventsPanel onLprTriggered={onLprTriggered} />)

    const button = screen.getByRole('button', { name: /LPR helicopter/ })
    fireEvent.click(button)
    fireEvent.click(button) // a second click while pending must not send a second request

    expect(await screen.findByText('Triggering…')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/incidents\/lpr-helicopter$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')

    release(
      jsonResponse({
        id: 'LPR-ABCD1234',
        status: 'ACTIVE',
        origin: 'MANUAL',
        started_at: '2026-11-13T12:00:00Z',
        ends_at: '2026-11-13T12:03:00Z',
        position: [18.46, 54.3925],
        route_start: [18.46, 54.3925],
        route_end: [18.67, 54.3925],
        speed_ms: 80,
        radius_m: 500,
        hold_margin_m: 250,
      }),
    )

    expect(await screen.findByText(/LPR helicopter started/)).toHaveTextContent(
      'drones in its way wait until it has passed',
    )
    expect(onLprTriggered).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the control while a helicopter is crossing, so none is started twice', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<SimulationEventsPanel lprActive />)

    const button = screen.getByRole('button', { name: /LPR helicopter/ })

    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Helicopter in transit')
    fireEvent.click(button)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows "already active" as information, not as an error or a new start', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'LPR_ALREADY_ACTIVE', message: 'Already active' } }, 409),
        ),
      ),
    )
    const onLprTriggered = vi.fn()
    render(<SimulationEventsPanel onLprTriggered={onLprTriggered} />)

    fireEvent.click(screen.getByRole('button', { name: /LPR helicopter/ }))

    expect(await screen.findByText('An LPR helicopter is already crossing the area.')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/LPR helicopter started/)).not.toBeInTheDocument()
    await waitFor(() => expect(onLprTriggered).toHaveBeenCalledTimes(1))
  })

  it('shows any other failure of the LPR request as an error, never as a start', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    render(<SimulationEventsPanel />)

    fireEvent.click(screen.getByRole('button', { name: /LPR helicopter/ }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText(/LPR helicopter started/)).not.toBeInTheDocument()
  })

  it('keeps the order when the operator backs out', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<SimulationEventsPanel selectedOrder={order('READY_FOR_PICKUP')} />)
    fireEvent.click(cancelButton())

    fireEvent.click(screen.getByRole('button', { name: 'Keep order' }))

    expect(screen.queryByRole('group', { name: 'Confirm cancellation' })).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('posts the cancellation once, shows success and asks the views to refresh', async () => {
    let release: (response: Response) => void = () => {}
    const fetchMock = vi.fn(
      (_url: string, _init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onOrderCancelled = vi.fn()
    render(
      <SimulationEventsPanel
        selectedOrder={order('READY_FOR_PICKUP')}
        onOrderCancelled={onOrderCancelled}
      />,
    )
    fireEvent.click(cancelButton())

    const confirm = screen.getByRole('button', { name: 'Confirm cancellation' })
    fireEvent.click(confirm)
    fireEvent.click(confirm) // a second click while pending must not send a second request

    expect(await screen.findByRole('button', { name: 'Cancelling…' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\/ORD-001\/cancel$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')

    release(
      jsonResponse({
        ...ORDER_RESPONSES[0],
        status: 'CANCELLED',
        cancelled_at: '2026-11-13T12:00:00Z',
      }),
    )

    expect(await screen.findByText('Order ORD-001 cancelled.')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Confirm cancellation' })).not.toBeInTheDocument()
    expect(onOrderCancelled).toHaveBeenCalledTimes(1)
  })

  it('shows the backend refusal, keeps the confirmation and still refreshes the views', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            { detail: { code: 'ORDER_ALREADY_DELIVERED', message: 'Order is already delivered' } },
            409,
          ),
        ),
      ),
    )
    const onOrderCancelled = vi.fn()
    render(
      <SimulationEventsPanel
        selectedOrder={order('OUT_FOR_DELIVERY')}
        onOrderCancelled={onOrderCancelled}
      />,
    )
    fireEvent.click(cancelButton())

    fireEvent.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/delivered/i)
    await waitFor(() => expect(onOrderCancelled).toHaveBeenCalledTimes(1))
    expect(screen.queryByText('Order ORD-001 cancelled.')).not.toBeInTheDocument()
  })
})
