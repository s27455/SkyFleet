import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ORDER_RESPONSES } from '../test/orderFixtures'
import { ApiError } from './client'
import { cancelOrder, generateOrder, getActiveOrders, getOrders } from './orders'

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('getOrders', () => {
  it('requests the orders endpoint and maps all ten orders in API order', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES)))

    const orders = await getOrders()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders$/)
    expect(orders.map((order) => order.id)).toEqual(ORDER_RESPONSES.map((order) => order.id))
    expect(orders).toHaveLength(10)
  })

  it('maps identity, Hub, destination, real coordinates, weight, status and timestamps', async () => {
    stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES)))

    const [first] = await getOrders()

    expect(first).toEqual({
      id: 'ORD-001',
      originHubId: 'hub-galeria-baltycka',
      destinationAddress: 'ul. Grunwaldzka 82, Gdańsk',
      coordinates: [18.5972, 54.3768], // [longitude, latitude], unchanged
      packageWeightKg: 0.8,
      status: 'READY_FOR_PICKUP',
      deliveredAt: null,
      cancelledAt: null,
      createdAt: '2026-11-11T21:53:08.077240Z',
      updatedAt: '2026-11-11T21:53:08.077240Z',
    })
    expect(first).not.toHaveProperty('assignedDroneId')
  })

  it('accepts an empty list', async () => {
    stubFetch(() => Promise.resolve(jsonResponse([])))

    await expect(getOrders()).resolves.toEqual([])
  })

  it.each(['CREATED', 'AWAITING_HANDOVER', 'READY_FOR_PICKUP'])(
    'accepts status %s',
    async (status) => {
      stubFetch(() => Promise.resolve(jsonResponse([{ ...ORDER_RESPONSES[0], status }])))

      await expect(getOrders()).resolves.toHaveLength(1)
    },
  )

  it.each<[string, Record<string, unknown>]>([
    ['unknown status', { status: 'RETURNED' }],
    ['missing id', { id: '' }],
    ['missing origin hub', { origin_hub_id: '' }],
    ['blank address', { destination_address: '   ' }],
    ['longitude out of range', { destination_longitude: 181 }],
    ['latitude out of range', { destination_latitude: -91 }],
    ['string coordinate', { destination_latitude: '54.3' }],
    ['null weight', { package_weight_kg: null }],
    ['zero weight', { package_weight_kg: 0 }],
    ['negative weight', { package_weight_kg: -1 }],
    ['bad created_at', { created_at: 'yesterday' }],
    ['created_at without a time zone', { created_at: '2026-11-11T21:53:08' }],
    ['missing updated_at', { updated_at: undefined }],
  ])('rejects the whole list for %s', async (_name, patch) => {
    stubFetch(() =>
      Promise.resolve(jsonResponse([ORDER_RESPONSES[1], { ...ORDER_RESPONSES[0], ...patch }])),
    )

    await expect(getOrders()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects a non-list payload, a non-object item and duplicate ids', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ orders: [] })))
    await expect(getOrders()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.resolve(jsonResponse([42])))
    await expect(getOrders()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.resolve(jsonResponse([ORDER_RESPONSES[0], ORDER_RESPONSES[0]])))
    await expect(getOrders()).rejects.toThrow(/duplicate/)
  })

  it('rejects on a server error and on a network failure', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'oops' }, 500)))
    await expect(getOrders()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    await expect(getOrders()).rejects.toBeInstanceOf(ApiError)
  })
})

describe('delivered_at and the active scope (Feature 017A)', () => {
  it('maps a delivery time and a legacy null, and rejects a bad or zone-less one', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse([
          { ...ORDER_RESPONSES[0], status: 'DELIVERED', delivered_at: '2026-11-13T12:00:00Z' },
          { ...ORDER_RESPONSES[1], status: 'DELIVERED', delivered_at: null },
        ]),
      ),
    )
    const [flown, legacy] = await getOrders()
    expect(flown.deliveredAt).toBe('2026-11-13T12:00:00Z')
    expect(legacy.deliveredAt).toBeNull()

    for (const bad of ['yesterday', '2026-11-13T12:00:00', 5]) {
      stubFetch(() => Promise.resolve(jsonResponse([{ ...ORDER_RESPONSES[0], delivered_at: bad }])))
      await expect(getOrders()).rejects.toBeInstanceOf(ApiError)
    }
  })

  it('asks the backend for the active orders only with active=true; getOrders stays unfiltered', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES)))

    await getActiveOrders()
    await getOrders()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\?active=true$/)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/orders$/)
  })
})

describe('generateOrder', () => {
  it('posts to the generate endpoint without a body and maps the created order', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(jsonResponse({ ...ORDER_RESPONSES[0], id: 'ORD-ABC12345' }, 201)),
    )
    vi.stubGlobal('fetch', fetchMock)

    const order = await generateOrder()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\/generate$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
    expect(order.id).toBe('ORD-ABC12345')
    expect(order.status).toBe('READY_FOR_PICKUP')
  })

  it('rejects an invalid answer and a server error', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ id: 'ORD-1' }, 201)))
    await expect(generateOrder()).rejects.toBeInstanceOf(ApiError)

    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'oops' }, 500)))
    await expect(generateOrder()).rejects.toBeInstanceOf(ApiError)
  })
})

describe('cancelOrder (Feature 018B)', () => {
  it('posts to the cancel endpoint without a body and maps the cancelled order', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(
        jsonResponse({
          ...ORDER_RESPONSES[0],
          status: 'CANCELLED',
          cancelled_at: '2026-11-13T12:00:00Z',
        }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const order = await cancelOrder('ORD-001')

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/orders\/ORD-001\/cancel$/)
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
    expect(order.status).toBe('CANCELLED')
    expect(order.cancelledAt).toBe('2026-11-13T12:00:00Z')
  })

  it('rejects a conflict and a zone-less cancellation time', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ detail: { code: 'ORDER_ALREADY_DELIVERED', message: 'delivered' } }, 409),
        ),
      ),
    )
    await expect(cancelOrder('ORD-001')).rejects.toBeInstanceOf(ApiError)

    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            ...ORDER_RESPONSES[0],
            status: 'CANCELLED',
            cancelled_at: '2026-11-13T12:00:00',
          }),
        ),
      ),
    )
    await expect(cancelOrder('ORD-001')).rejects.toBeInstanceOf(ApiError)
  })
})
