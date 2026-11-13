import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { ORDER_RESPONSES } from '../../test/orderFixtures'
import type { Order, OrderStatus } from '../../types/order'
import { CancelOrderAction } from './CancelOrderAction'

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

const cancelled = () =>
  jsonResponse({
    ...ORDER_RESPONSES[0],
    status: 'CANCELLED',
    cancelled_at: '2026-11-13T12:00:00Z',
  })

describe('CancelOrderAction', () => {
  it.each<OrderStatus>(['READY_FOR_PICKUP', 'OUT_FOR_DELIVERY'])(
    'offers a visible Cancel order button for a %s order and sends nothing yet',
    (status) => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)
      render(<CancelOrderAction order={order(status)} onCancelled={() => {}} />)

      fireEvent.click(screen.getByRole('button', { name: 'Cancel order' }))

      expect(screen.getByRole('group', { name: 'Confirm cancellation' })).toHaveTextContent(
        'permanent',
      )
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it.each<OrderStatus>(['DELIVERED', 'CANCELLED'])('offers nothing for a %s order', (status) => {
    render(<CancelOrderAction order={order(status)} onCancelled={() => {}} />)

    expect(screen.queryByRole('button', { name: 'Cancel order' })).not.toBeInTheDocument()
  })

  it('explains the recall for an order that is out for delivery', () => {
    render(<CancelOrderAction order={order('OUT_FOR_DELIVERY')} onCancelled={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel order' }))

    expect(screen.getByRole('group', { name: 'Confirm cancellation' })).toHaveTextContent(
      'return to the nearest reachable Hub',
    )
  })

  it('sends one request on confirmation, shows pending, and reports back', async () => {
    let release: (response: Response) => void = () => {}
    const fetchMock = vi.fn(
      (_url: string, _init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onCancelled = vi.fn()
    render(<CancelOrderAction order={order('READY_FOR_PICKUP')} onCancelled={onCancelled} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel order' }))

    const confirm = screen.getByRole('button', { name: 'Confirm cancellation' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(await screen.findByRole('button', { name: 'Cancelling…' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\/ORD-001\/cancel$/)

    release(cancelled())

    await waitFor(() => expect(onCancelled).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('group', { name: 'Confirm cancellation' })).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a refusal as an error, never as a success, and still refreshes the views', async () => {
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
    const onCancelled = vi.fn()
    render(<CancelOrderAction order={order('OUT_FOR_DELIVERY')} onCancelled={onCancelled} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel order' }))

    fireEvent.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/delivered/i)
    expect(screen.queryByText(/cancelled/i)).not.toBeInTheDocument()
    await waitFor(() => expect(onCancelled).toHaveBeenCalledTimes(1))
    // The confirmation stays so the operator can see what was refused and decide again.
    expect(screen.getByRole('group', { name: 'Confirm cancellation' })).toBeInTheDocument()
  })

  it('shows a network failure as an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    render(<CancelOrderAction order={order('READY_FOR_PICKUP')} onCancelled={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel order' }))

    fireEvent.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('keeps the order when the operator backs out', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<CancelOrderAction order={order('READY_FOR_PICKUP')} onCancelled={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel order' }))

    fireEvent.click(screen.getByRole('button', { name: 'Keep order' }))

    expect(screen.getByRole('button', { name: 'Cancel order' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
