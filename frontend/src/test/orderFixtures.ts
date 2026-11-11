import type { OrderResponse } from '../types/order'

const ORIGIN_HUBS = [
  'hub-galeria-baltycka',
  'hub-galeria-baltycka',
  'hub-galeria-baltycka',
  'hub-forum-gdansk',
  'hub-forum-gdansk',
  'hub-forum-gdansk',
  'hub-centrum-riviera',
  'hub-centrum-riviera',
  'hub-centrum-handlowe-osowa',
  'hub-centrum-handlowe-osowa',
]

/** (address, longitude, latitude, weight) per seeded order, as Feature 007 seeds them. */
const DESTINATIONS: [string, number, number, number][] = [
  ['ul. Grunwaldzka 82, Gdańsk', 18.5972, 54.3768, 0.8],
  ['ul. Do Studzienki 25, Gdańsk', 18.5887, 54.3881, 1.5],
  ['ul. Słowackiego 200, Gdańsk', 18.612, 54.3935, 2.2],
  ['ul. Długa 45, Gdańsk', 18.6531, 54.3487, 0.3],
  ['ul. Chmielna 10, Gdańsk', 18.641, 54.3512, 1.1],
  ['ul. Podwale Staromiejskie 60, Gdańsk', 18.6459, 54.3558, 3.0],
  ['ul. Świętojańska 30, Gdynia', 18.544, 54.5189, 0.6],
  ['ul. Morska 59, Gdynia', 18.512, 54.505, 2.4],
  ['ul. Spacerowa 12, Gdańsk', 18.4952, 54.4311, 1.9],
  ['ul. Kielnieńska 5, Gdańsk', 18.472, 54.418, 0.5],
]

/** The ten seeded orders as `GET /api/orders` returns them (ordered by id). Test data only. */
export const ORDER_RESPONSES: OrderResponse[] = DESTINATIONS.map(
  ([address, longitude, latitude, weight], index) => ({
    id: `ORD-${String(index + 1).padStart(3, '0')}`,
    origin_hub_id: ORIGIN_HUBS[index],
    destination_address: address,
    destination_longitude: longitude,
    destination_latitude: latitude,
    package_weight_kg: weight,
    status: 'READY_FOR_PICKUP' as const,
    created_at: '2026-11-11T21:53:08.077240Z',
    updated_at: '2026-11-11T21:53:08.077240Z',
  }),
)
