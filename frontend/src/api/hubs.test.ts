import { describe, expect, it, vi } from 'vitest'

import { HUB_RESPONSES, jsonResponse } from '../test/hubFixtures'
import { ApiError } from './client'
import { getHubs } from './hubs'

function stubFetch(response: () => Promise<Response>) {
  const fetchMock = vi.fn((_url: string) => response())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('getHubs', () => {
  it('requests the hubs endpoint and maps the four hubs', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(HUB_RESPONSES)))

    const hubs = await getHubs()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/hubs$/)
    expect(hubs.map((hub) => hub.id)).toEqual(HUB_RESPONSES.map((hub) => hub.id))
    expect(hubs[2]).toEqual({
      id: 'hub-forum-gdansk',
      name: 'Forum Gdańsk',
      address: 'Targ Sienny 7, Gdańsk',
      coordinates: [18.643527, 54.349346],
      droneCapacity: 50,
    })
  })

  it('maps coordinates to [longitude, latitude] for every hub', async () => {
    stubFetch(() => Promise.resolve(jsonResponse(HUB_RESPONSES)))

    const hubs = await getHubs()

    hubs.forEach((hub, index) => {
      expect(hub.coordinates).toEqual([
        HUB_RESPONSES[index].longitude,
        HUB_RESPONSES[index].latitude,
      ])
      expect(hub.coordinates[0]).toBeLessThan(hub.coordinates[1]) // lng ~18 < lat ~54
    })
  })

  it('accepts an empty list', async () => {
    stubFetch(() => Promise.resolve(jsonResponse([])))

    await expect(getHubs()).resolves.toEqual([])
  })

  it('rejects with ApiError on an HTTP error status', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'boom' }, 500)))

    await expect(getHubs()).rejects.toMatchObject({ name: 'ApiError', status: 500 })
  })

  it('rejects with ApiError when the backend is unreachable', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))

    await expect(getHubs()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects with ApiError when a 200 response is not valid JSON', async () => {
    stubFetch(() => Promise.resolve(new Response('<html>proxy page</html>', { status: 200 })))

    await expect(getHubs()).rejects.toBeInstanceOf(ApiError)
  })

  const [valid] = HUB_RESPONSES
  it.each([
    ['not a list', { hubs: [] }],
    ['an item that is not an object', [null]],
    ['a missing id', [{ ...valid, id: undefined }]],
    ['a missing name', [{ ...valid, name: '' }]],
    ['a missing address', [{ ...valid, address: undefined }]],
    ['a string longitude', [{ ...valid, longitude: '18.5' }]],
    ['a longitude out of range', [{ ...valid, longitude: 181 }]],
    ['a latitude out of range', [{ ...valid, latitude: -91 }]],
    ['a missing drone_capacity', [{ ...valid, drone_capacity: undefined }]],
    ['a non-positive drone_capacity', [{ ...valid, drone_capacity: 0 }]],
    ['a fractional drone_capacity', [{ ...valid, drone_capacity: 2.5 }]],
    ['duplicate ids', [valid, valid]],
  ])('rejects malformed data: %s', async (_name, payload) => {
    stubFetch(() => Promise.resolve(jsonResponse(payload)))

    await expect(getHubs()).rejects.toBeInstanceOf(ApiError)
  })
})
