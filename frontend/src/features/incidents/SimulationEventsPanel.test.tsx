import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { ORDER_RESPONSES } from '../../test/orderFixtures'
import type { Order, OrderStatus } from '../../types/order'
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
  createdAt: '2026-11-11T21:53:08Z',
  updatedAt: '2026-11-11T21:53:08Z',
})

const cancelButton = () => screen.getByRole('button', { name: /Cancel order/ })
const confirmation = () => screen.getByRole('group', { name: 'Confirm cancellation' })

describe('SimulationEventsPanel', () => {
  it('shows the two future scenarios as named, disabled controls with their feature', () => {
    render(<SimulationEventsPanel />)

    const expected: [string, string][] = [
      ['Recipient unavailable', '018D'],
      ['LPR transit', '018E'],
    ]
    for (const [label, feature] of expected) {
      const button = screen.getByRole('button', { name: new RegExp(label) })
      expect(button).toBeDisabled()
      expect(button).toHaveTextContent(`Coming in ${feature}`)
    }
  })

  it('shows Random incidents off, disabled and honestly explained', () => {
    render(<SimulationEventsPanel />)

    const toggle = screen.getByRole('switch', { name: 'Random incidents' })
    expect(toggle).toBeDisabled()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Available when incident scenarios are enabled.')).toBeInTheDocument()
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
