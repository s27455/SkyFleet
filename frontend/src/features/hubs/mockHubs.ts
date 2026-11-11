import type { Hub } from '../../types/hub'

const INITIAL_DRONE_CAPACITY = 50

// Coordinates are [lng, lat] of the mall buildings (for visualization only, not launch pads).
// The malls are illustrative, not real SkyFleet facilities.
export const MOCK_HUBS: readonly Hub[] = [
  {
    id: 'hub-galeria-baltycka',
    name: 'Galeria Bałtycka',
    city: 'Gdańsk',
    coordinates: [18.6006944, 54.3826244],
    status: 'operational',
    droneCapacity: INITIAL_DRONE_CAPACITY,
  },
  {
    id: 'hub-forum-gdansk',
    name: 'Forum Gdańsk',
    city: 'Gdańsk',
    coordinates: [18.643527, 54.349346],
    status: 'operational',
    droneCapacity: INITIAL_DRONE_CAPACITY,
  },
  {
    id: 'hub-centrum-riviera',
    name: 'Centrum Riviera',
    city: 'Gdynia',
    coordinates: [18.5317863, 54.5046621],
    status: 'operational',
    droneCapacity: INITIAL_DRONE_CAPACITY,
  },
  {
    id: 'hub-centrum-handlowe-osowa',
    name: 'Centrum Handlowe Osowa',
    city: 'Gdańsk',
    coordinates: [18.49097, 54.42569],
    status: 'operational',
    droneCapacity: INITIAL_DRONE_CAPACITY,
  },
]

/** Hub source for the UI. Phase 4 replaces this with a backend API call. */
export function getHubs(): readonly Hub[] {
  return MOCK_HUBS
}
