/* oxlint-disable react/only-export-components, react/immutability -- test stand-ins that record calls on purpose */
import { useEffect } from 'react'

import type { FlightVisual } from '../features/flights/interpolation'
import type { FocusRequest } from '../features/map/focusTarget'
import type { Drone } from '../types/drone'
import type { Hub } from '../types/hub'
import type { Order } from '../types/order'

// Stand-ins for the two WebGL components, shared by the App test files. Each test file registers
// them with vi.mock(path, async () => ({ X: (await import('./test/appMocks')).XStub })).

// Every distinct focus command (Feature 023) the app hands to the map, in order.
export const mapFocus = { requests: [] as unknown[], last: null as unknown }

// The real map needs WebGL. This stand-in renders one button per Hub (exposing its docked count) and
// per drone it is given, so the tests can assert exactly what reaches the map and how selection
// flows back.
export function MapViewStub({
  hubs = [],
  selectedHubId = null,
  onSelectHub,
  drones = [],
  dockedCounts = new Map(),
  selectedDroneId = null,
  onSelectDrone,
  orders = [],
  selectedOrderId = null,
  onSelectOrder,
  flights = [],
  focusRequest = null,
}: {
  focusRequest?: FocusRequest | null
  hubs?: readonly Hub[]
  selectedHubId?: string | null
  onSelectHub?: (id: string) => void
  drones?: readonly Drone[]
  dockedCounts?: ReadonlyMap<string, number>
  selectedDroneId?: string | null
  onSelectDrone?: (id: string) => void
  orders?: readonly Order[]
  selectedOrderId?: string | null
  onSelectOrder?: (id: string) => void
  flights?: readonly FlightVisual[]
}) {
  if (focusRequest && mapFocus.last !== focusRequest) {
    mapFocus.last = focusRequest
    mapFocus.requests.push(focusRequest)
  }
  return (
    <div
      data-testid="map"
      data-flight-drones={flights.map((flight) => flight.droneId).join(',')}
      data-flight-animate={flights.map((flight) => String(flight.animate)).join(',')}
    >
      {hubs.map((hub) => (
        <button
          key={hub.id}
          type="button"
          aria-pressed={hub.id === selectedHubId}
          data-docked-count={dockedCounts.get(hub.id) ?? 0}
          onClick={() => onSelectHub?.(hub.id)}
        >
          {`Marker ${hub.name}`}
        </button>
      ))}
      {drones.map((drone) => (
        <button
          key={drone.id}
          type="button"
          aria-pressed={drone.id === selectedDroneId}
          onClick={() => onSelectDrone?.(drone.id)}
        >
          {`Drone marker ${drone.id}`}
        </button>
      ))}
      {orders.map((order) => (
        <button
          key={order.id}
          type="button"
          aria-pressed={order.id === selectedOrderId}
          onClick={() => onSelectOrder?.(order.id)}
        >
          {`Order marker ${order.id}`}
        </button>
      ))}
    </div>
  )
}

// The 3D viewer needs WebGL; the inspector tests only care that it is mounted (and how often).
export const viewerMounts = { count: 0 }

export function Drone3DViewerStub() {
  useEffect(() => {
    viewerMounts.count += 1
  }, [])
  return <div data-testid="viewer" />
}
