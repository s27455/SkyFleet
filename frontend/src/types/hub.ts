/** Mirrors `HubResponse` in backend/app/hubs/schemas.py (snake_case JSON from `GET /api/hubs`). */
export interface HubResponse {
  id: string
  name: string
  address: string
  longitude: number
  latitude: number
  drone_capacity: number
}

/** Mall Pickup Hub: parcel handover point and drone base (business-rules.md §2). */
export interface Hub {
  /** Stable slug assigned by the backend, e.g. `hub-forum-gdansk`. */
  id: string
  name: string
  address: string
  /** [lng, lat], the order Mapbox expects. */
  coordinates: [number, number]
  /** Maximum number of drones the Hub can accommodate (not parcels or orders). */
  droneCapacity: number
}
