import type { HubResponse } from '../types/hub'

/** The four seeded Hubs as `GET /api/hubs` returns them (ordered by id). Test data only. */
export const HUB_RESPONSES: HubResponse[] = [
  {
    id: 'hub-centrum-handlowe-osowa',
    name: 'Centrum Handlowe Osowa',
    address: 'Spacerowa 48, 80-299 Gdańsk',
    longitude: 18.49097,
    latitude: 54.42569,
    drone_capacity: 50,
  },
  {
    id: 'hub-centrum-riviera',
    name: 'Centrum Riviera',
    address: 'Kazimierza Górskiego 2, Gdynia',
    longitude: 18.5317863,
    latitude: 54.5046621,
    drone_capacity: 50,
  },
  {
    id: 'hub-forum-gdansk',
    name: 'Forum Gdańsk',
    address: 'Targ Sienny 7, Gdańsk',
    longitude: 18.643527,
    latitude: 54.349346,
    drone_capacity: 50,
  },
  {
    id: 'hub-galeria-baltycka',
    name: 'Galeria Bałtycka',
    address: 'al. Grunwaldzka 141, Gdańsk',
    longitude: 18.6006944,
    latitude: 54.3826244,
    drone_capacity: 50,
  },
]

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}
