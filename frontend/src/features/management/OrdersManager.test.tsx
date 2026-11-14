import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../../test/hubFixtures'
import { ORDER_RESPONSES } from '../../test/orderFixtures'
import { toOrder } from '../../api/orders'
import type { Hub } from '../../types/hub'
import type { Mission } from '../../types/mission'
import type { Order } from '../../types/order'
import { OrdersManager } from './OrdersManager'

const HUBS: Hub[] = [
  {
    id: 'hub-forum-gdansk',
    name: 'Forum Gdańsk',
    address: 'Targ Sienny 7',
    coordinates: [18.64, 54.35],
    droneCapacity: 50,
  },
  {
    id: 'hub-centrum-riviera',
    name: 'Riviera',
    address: 'Kielecka 39',
    coordinates: [18.55, 54.52],
    droneCapacity: 50,
  },
]

const ORDERS: Order[] = [
  toOrder(ORDER_RESPONSES[3]), // ORD-004, free
  toOrder(ORDER_RESPONSES[4]), // ORD-005, has a mission
  toOrder({ ...ORDER_RESPONSES[5], status: 'DELIVERED' }), // ORD-006, not editable
]

const MISSIONS: Mission[] = [
  {
    id: 'MIS-1',
    orderId: 'ORD-005',
    purpose: 'DELIVERY',
    droneId: 'DRN-001',
    originHubId: 'hub-forum-gdansk',
    returnHubId: 'hub-forum-gdansk',
    status: 'CANCELLED',
    totalKm: 3,
  },
]

function renderManager(orders: Order[] = ORDERS) {
  const onChanged = vi.fn()
  render(<OrdersManager orders={orders} hubs={HUBS} missions={MISSIONS} onChanged={onChanged} />)
  return { onChanged }
}

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function fillForm() {
  fireEvent.change(screen.getByLabelText('Delivery address'), { target: { value: 'ul. Nowa 3' } })
  fireEvent.change(screen.getByLabelText('Delivery longitude'), { target: { value: '18.7' } })
  fireEvent.change(screen.getByLabelText('Delivery latitude'), { target: { value: '54.4' } })
  fireEvent.change(screen.getByLabelText(/Package weight/), { target: { value: '1.2' } })
}

describe('OrdersManager', () => {
  it('lists orders and disables Edit and Delete for ineligible ones', () => {
    renderManager()

    expect(screen.getByText('ORD-004')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit order ORD-004' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Delete order ORD-004' })).toBeEnabled()
    // has a mission (any status)
    expect(screen.getByRole('button', { name: 'Edit order ORD-005' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Delete order ORD-005' })).toBeDisabled()
    // not READY_FOR_PICKUP
    expect(screen.getByRole('button', { name: 'Edit order ORD-006' })).toBeDisabled()
  })

  it('selects an order from the table so the Cancel order shortcut can act on it', () => {
    const onSelectOrder = vi.fn()
    render(
      <OrdersManager
        orders={ORDERS}
        hubs={HUBS}
        missions={MISSIONS}
        onChanged={vi.fn()}
        selectedOrderId="ORD-005"
        onSelectOrder={onSelectOrder}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Select order ORD-004' }))

    expect(onSelectOrder).toHaveBeenCalledWith('ORD-004')
    expect(screen.getByRole('button', { name: 'Select order ORD-005' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('shows a cancelled order with its status in words', () => {
    renderManager([toOrder({ ...ORDER_RESPONSES[3], status: 'CANCELLED' })])

    expect(screen.getByText('Cancelled')).toBeInTheDocument()
  })

  it('shows an empty state for the active view', () => {
    renderManager([])

    expect(screen.getByText(/No active orders/)).toBeInTheDocument()
  })

  it('defaults to Active and reads the full history only after All is chosen', async () => {
    const history = [
      ...ORDER_RESPONSES.slice(3, 5),
      { ...ORDER_RESPONSES[5], status: 'DELIVERED', delivered_at: '2026-11-13T10:00:00Z' },
      { ...ORDER_RESPONSES[6], status: 'DELIVERED', delivered_at: null },
    ]
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(history)))
    renderManager()

    expect(screen.getByRole('heading', { name: 'Active orders (3)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Active' })).toHaveAttribute('aria-pressed', 'true')
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    expect(await screen.findByRole('heading', { name: 'All orders (4)' })).toBeInTheDocument()
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders$/)
    expect(screen.getByText('ORD-007')).toBeInTheDocument() // legacy delivered order, still listed
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Active' }))

    expect(screen.getByRole('heading', { name: 'Active orders (3)' })).toBeInTheDocument()
    expect(screen.queryByText('ORD-007')).not.toBeInTheDocument()
  })

  it('shows an error with Retry when the history cannot be read', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'oops' }, 500)))
    renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load all orders')
    fireEvent.click(screen.getByRole('button', { name: 'Show active orders' }))
    expect(screen.getByRole('heading', { name: 'Active orders (3)' })).toBeInTheDocument()
  })

  it('creates an order, then refreshes the data and closes the form', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES[0], 201)))
    const { onChanged } = renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'New order' }))
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Create order' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      origin_hub_id: 'hub-forum-gdansk',
      destination_address: 'ul. Nowa 3',
      destination_longitude: 18.7,
      destination_latitude: 54.4,
      package_weight_kg: 1.2,
    })
    expect(screen.queryByRole('form', { name: 'Create order' })).not.toBeInTheDocument()
  })

  it('checks required fields locally without calling the backend', () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({})))
    renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'New order' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create order' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Enter a delivery address.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows the backend validation error and keeps the form open', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse(
          {
            detail: [
              {
                loc: ['body', 'package_weight_kg'],
                msg: 'Input should be less than or equal to 3',
              },
            ],
          },
          422,
        ),
      ),
    )
    const { onChanged } = renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'New order' }))
    fillForm()
    fireEvent.change(screen.getByLabelText(/Package weight/), { target: { value: '9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create order' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('package_weight_kg: Input should')
    expect(onChanged).not.toHaveBeenCalled()
    expect(screen.getByRole('form', { name: 'Create order' })).toBeInTheDocument()
  })

  it('sends one request however often the submit button is clicked', async () => {
    let release: (response: Response) => void = () => undefined
    const fetchMock = stubFetch(() => new Promise<Response>((resolve) => (release = resolve)))
    renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'New order' }))
    fillForm()
    const submit = screen.getByRole('button', { name: 'Create order' })
    fireEvent.click(submit)
    fireEvent.click(submit)
    fireEvent.click(submit)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
    release(jsonResponse(ORDER_RESPONSES[0], 201))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Saving…' })).toBeNull())
  })

  it('edits an eligible order with only its form values', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES[3])))
    const { onChanged } = renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'Edit order ORD-004' }))
    fireEvent.change(screen.getByLabelText(/Package weight/), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/orders\/ORD-004$/)
    expect(init?.method).toBe('PATCH')
  })

  it('requires confirmation before deleting, then deletes and refreshes', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(new Response(null, { status: 204 })))
    const { onChanged } = renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'Delete order ORD-004' }))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toHaveTextContent('ORD-004')

    fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE')
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('shows the backend refusal when a delete is rejected', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse(
          { detail: { code: 'ORDER_HAS_MISSIONS', message: 'Order is referenced by a mission' } },
          409,
        ),
      ),
    )
    const { onChanged } = renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'Delete order ORD-004' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Order is referenced by a mission')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('cancelling the confirmation deletes nothing', () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({})))
    renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'Delete order ORD-004' }))
    fireEvent.click(screen.getByRole('button', { name: 'Keep' }))

    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('shows the backend refusal when an edit is rejected and keeps the form open', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse(
          { detail: { code: 'ORDER_NOT_EDITABLE', message: 'Order is no longer editable' } },
          409,
        ),
      ),
    )
    const { onChanged } = renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'Edit order ORD-004' }))
    fireEvent.change(screen.getByLabelText(/Package weight/), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Order is no longer editable')
    expect(onChanged).not.toHaveBeenCalled()
    expect(screen.getByRole('form', { name: 'Edit order ORD-004' })).toBeInTheDocument()
  })

  it('refuses an unchanged edit locally', () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({})))
    renderManager()

    fireEvent.click(screen.getByRole('button', { name: 'Edit order ORD-004' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Nothing has changed.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('closes an open form when its order disappears from the data', () => {
    const onChanged = vi.fn()
    const { rerender } = render(
      <OrdersManager orders={ORDERS} hubs={HUBS} missions={MISSIONS} onChanged={onChanged} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Edit order ORD-004' }))
    expect(screen.getByRole('form', { name: 'Edit order ORD-004' })).toBeInTheDocument()

    rerender(
      <OrdersManager
        orders={ORDERS.slice(1)}
        hubs={HUBS}
        missions={MISSIONS}
        onChanged={onChanged}
      />,
    )
    rerender(
      <OrdersManager orders={ORDERS} hubs={HUBS} missions={MISSIONS} onChanged={onChanged} />,
    )

    expect(screen.queryByRole('form', { name: 'Edit order ORD-004' })).not.toBeInTheDocument()
  })
})
