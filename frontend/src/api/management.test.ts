import { describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '../test/hubFixtures'
import { ORDER_RESPONSES } from '../test/orderFixtures'
import { ApiError, describeApiError } from './client'
import { createOrder, deleteOrder, updateOrder } from './orders'

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string, _init?: RequestInit) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const INPUT = {
  originHubId: 'hub-forum-gdansk',
  destinationAddress: 'ul. Testowa 1, Gdańsk',
  longitude: 18.65,
  latitude: 54.35,
  packageWeightKg: 1.5,
}

describe('order writes', () => {
  it('POSTs the snake_case body and maps the created order', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES[0], 201)))

    const order = await createOrder(INPUT)

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/orders$/)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({
      origin_hub_id: 'hub-forum-gdansk',
      destination_address: 'ul. Testowa 1, Gdańsk',
      destination_longitude: 18.65,
      destination_latitude: 54.35,
      package_weight_kg: 1.5,
    })
    expect(order.id).toBe('ORD-001')
  })

  it('PATCHes only the changed fields', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(ORDER_RESPONSES[0])))

    await updateOrder('ORD-001', { packageWeightKg: 2 })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/orders\/ORD-001$/)
    expect(init?.method).toBe('PATCH')
    expect(JSON.parse(String(init?.body))).toEqual({ package_weight_kg: 2 })
  })

  it('DELETEs and resolves on 204 without a body', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(new Response(null, { status: 204 })))

    await expect(deleteOrder('ORD-001')).resolves.toBeUndefined()

    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE')
  })

  it('rejects with the backend detail on a conflict', async () => {
    stubFetch(() =>
      Promise.resolve(
        jsonResponse({ detail: { code: 'ORDER_HAS_MISSIONS', message: 'Has missions' } }, 409),
      ),
    )

    const error = await deleteOrder('ORD-001').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(409)
    expect(describeApiError(error)).toBe('Has missions')
  })
})

describe('describeApiError', () => {
  it('summarises FastAPI validation errors by field', () => {
    const error = new ApiError('x', 422, [
      { loc: ['body', 'package_weight_kg'], msg: 'Input should be less than or equal to 3' },
    ])

    expect(describeApiError(error)).toBe(
      'package_weight_kg: Input should be less than or equal to 3',
    )
  })

  it('reports an unreachable backend and unknown errors without leaking details', () => {
    expect(describeApiError(new ApiError('Backend is unreachable'))).toBe('Backend is unreachable')
    expect(describeApiError(new Error('boom'))).toBe('Something went wrong. Please try again.')
    expect(describeApiError(new ApiError('x', 500, { surprise: true }))).toBe(
      'The backend rejected the request (status 500).',
    )
  })
})
