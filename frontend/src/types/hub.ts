/** Illustrative status only: the frontend never measures Hub state. */
export type HubStatus = 'operational' | 'limited' | 'offline'

/** Mall Pickup Hub: parcel handover point and drone base (business-rules.md §2). */
export interface Hub {
  id: string
  name: string
  city: string
  /** [lng, lat], the order Mapbox expects. */
  coordinates: [number, number]
  status: HubStatus
  /** Maximum number of drones the Hub can accommodate (not parcels or orders). */
  droneCapacity: number
}
