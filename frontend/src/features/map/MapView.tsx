import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { type ReactNode, useEffect, useRef, useState } from 'react'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { type FlightVisual, interpolatePosition } from '../flights/interpolation'
import {
  type PixelOffset,
  createDroneMarkerElement,
  droneMarkerLabel,
  setDroneMarkerSelected,
} from './droneMarkers'
import {
  createOrderMarkerElement,
  setOrderMarkerSelected,
  updateOrderMarkerElement,
} from './orderMarkers'
import { MAP_STYLE, TRICITY_BOUNDS, TRICITY_FIT_PADDING_PX, getMapboxToken } from './mapConfig'

type MapStatus = 'loading' | 'ready' | 'error'

function MapMessage({ role, children }: { role: 'status' | 'alert'; children: ReactNode }) {
  return (
    <div
      role={role}
      className="absolute inset-0 z-10 flex items-center justify-center bg-canvas p-4 text-center text-sm text-fg-muted"
    >
      <div className="max-w-sm">{children}</div>
    </div>
  )
}

const NO_HUBS: readonly Hub[] = []
const NO_DRONES: readonly Drone[] = []
const NO_ORDERS: readonly Order[] = []
const NO_FLIGHTS: readonly FlightVisual[] = []
const NO_COUNTS: ReadonlyMap<string, number> = new Map()
const NO_OFFSETS: ReadonlyMap<string, PixelOffset> = new Map()
const NO_PIXEL_OFFSET: PixelOffset = [0, 0]

const HUB_MARKER_CLASS =
  'z-10 flex size-10 items-center justify-center rounded-md border-2 border-accent shadow-md cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'
const HUB_MARKER_IDLE_CLASSES = ['bg-canvas', 'text-accent']
const HUB_MARKER_SELECTED_CLASSES = ['bg-accent', 'text-canvas']

function createHubMarkerElement(hub: Hub, onClick: () => void) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = HUB_MARKER_CLASS
  element.dataset.markerKind = 'hub'
  element.textContent = 'H'
  const badge = document.createElement('span')
  badge.dataset.droneBadge = ''
  badge.setAttribute('aria-hidden', 'true') // the count is part of the button's accessible name
  badge.className =
    'absolute -top-2 -right-2 flex h-5 min-w-5 items-center justify-center rounded-full border border-canvas bg-fg px-1 text-xs font-semibold tabular-nums text-canvas'
  element.appendChild(badge)
  element.addEventListener('click', onClick)
  setHubMarkerSelected(element, false)
  setHubDockedCount(element, hub, 0)
  return element
}

/** Updates the badge and accessible name in place; the badge is hidden when no drone is docked. */
function setHubDockedCount(element: HTMLElement, hub: Hub, count: number) {
  const badge = element.querySelector<HTMLElement>('[data-drone-badge]')
  if (badge) {
    badge.textContent = String(count)
    badge.hidden = count === 0
  }
  const drones = count === 0 ? '' : `, ${count} ${count === 1 ? 'drone' : 'drones'} docked`
  element.setAttribute('aria-label', `Hub: ${hub.name}, ${hub.address}${drones}`)
}

/** Updates the existing element in place so keyboard focus survives a selection change. */
function setHubMarkerSelected(element: HTMLElement, selected: boolean) {
  element.classList.remove(...(selected ? HUB_MARKER_IDLE_CLASSES : HUB_MARKER_SELECTED_CLASSES))
  element.classList.add(...(selected ? HUB_MARKER_SELECTED_CLASSES : HUB_MARKER_IDLE_CLASSES))
  element.setAttribute('aria-pressed', String(selected))
}

interface MapViewProps {
  hubs?: readonly Hub[]
  selectedHubId?: string | null
  onSelectHub?: (hubId: string) => void
  /** Drones that get their own marker (in flight, or away from every Hub). Docked ones are not here. */
  drones?: readonly Drone[]
  /** Number of docked drones per Hub id, shown as a badge on the Hub marker. */
  dockedCounts?: ReadonlyMap<string, number>
  selectedDroneId?: string | null
  onSelectDrone?: (droneId: string) => void
  /** Delivery orders; each gets a small destination marker at its real coordinates. */
  orders?: readonly Order[]
  selectedOrderId?: string | null
  onSelectOrder?: (orderId: string) => void
  /** Screen-space offsets (px) by order id for destinations sharing a point. Display only. */
  orderOffsets?: ReadonlyMap<string, PixelOffset>
  /** Screen-space offsets (px) by drone id for drones sharing a location. Display only. */
  droneOffsets?: ReadonlyMap<string, PixelOffset>
  /**
   * Backend flight snapshots of flying drones. Their markers are drawn at the snapshot and, where
   * `animate` is set, glide toward the backend's target between snapshots.
   */
  flights?: readonly FlightVisual[]
}

/**
 * Interactive Mapbox map filling its positioned parent (`absolute inset-0`).
 * Presentation only: it renders the Hubs and drones it is given and reports selection; it owns no
 * data. Drone markers sit at the drones' real coordinates; `droneOffsets` only shifts the marker
 * on screen so drones that share a point stay individually selectable.
 */
export function MapView({
  hubs = NO_HUBS,
  selectedHubId = null,
  onSelectHub,
  drones = NO_DRONES,
  dockedCounts = NO_COUNTS,
  selectedDroneId = null,
  onSelectDrone,
  droneOffsets = NO_OFFSETS,
  orders = NO_ORDERS,
  selectedOrderId = null,
  onSelectOrder,
  orderOffsets = NO_OFFSETS,
  flights = NO_FLIGHTS,
}: MapViewProps) {
  const token = getMapboxToken()
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const markerElementsRef = useRef(new Map<string, HTMLElement>())
  const droneElementsRef = useRef(new Map<string, HTMLElement>())
  const droneMarkersRef = useRef(new Map<string, mapboxgl.Marker>())
  const droneOffsetsRef = useRef(droneOffsets)
  const orderElementsRef = useRef(new Map<string, HTMLElement>())
  const orderMarkersRef = useRef(new Map<string, mapboxgl.Marker>())
  const orderOffsetsRef = useRef(orderOffsets)
  const ordersRef = useRef(orders)
  const onSelectOrderRef = useRef(onSelectOrder)
  const onSelectHubRef = useRef(onSelectHub)
  const onSelectDroneRef = useRef(onSelectDrone)
  const [status, setStatus] = useState<MapStatus>('loading')

  useEffect(() => {
    onSelectHubRef.current = onSelectHub
  }, [onSelectHub])

  useEffect(() => {
    onSelectDroneRef.current = onSelectDrone
  }, [onSelectDrone])

  useEffect(() => {
    onSelectOrderRef.current = onSelectOrder
  }, [onSelectOrder])

  useEffect(() => {
    ordersRef.current = orders
  }, [orders])

  // Markers are DOM-based (native keyboard/touch support); fine for a handful of Hubs.
  // They are rebuilt only when `hubs` changes, never on selection (see the effect below).
  useEffect(() => {
    const map = mapRef.current
    const elements = markerElementsRef.current
    if (status !== 'ready' || !map) return

    const markers = hubs.map((hub) => {
      const element = createHubMarkerElement(hub, () => onSelectHubRef.current?.(hub.id))
      elements.set(hub.id, element)
      return new mapboxgl.Marker({ element }).setLngLat(hub.coordinates).addTo(map)
    })

    return () => {
      markers.forEach((marker) => marker.remove())
      elements.clear()
    }
  }, [hubs, status])

  // Declared after the marker effect so it also styles freshly created markers.
  useEffect(() => {
    markerElementsRef.current.forEach((element, hubId) =>
      setHubMarkerSelected(element, hubId === selectedHubId),
    )
  }, [hubs, status, selectedHubId])

  // In place, so a count change never rebuilds the marker or drops keyboard focus.
  useEffect(() => {
    hubs.forEach((hub) => {
      const element = markerElementsRef.current.get(hub.id)
      if (element) setHubDockedCount(element, hub, dockedCounts.get(hub.id) ?? 0)
    })
  }, [hubs, status, dockedCounts])

  useEffect(() => {
    droneOffsetsRef.current = droneOffsets
  }, [droneOffsets])

  // The latest data, read by effects that must not be re-run on every update.
  const dronesRef = useRef(drones)
  const flightsRef = useRef(flights)
  useEffect(() => {
    dronesRef.current = drones
    flightsRef.current = flights
  }, [drones, flights])

  // Drone markers are keyed on *which* drones have a marker and of what kind, not on their data:
  // a flying drone's snapshot changes every second. A new snapshot only updates the existing
  // markers in place (below), so they keep their elements and keyboard focus. They are never
  // rebuilt on selection or because display offsets changed. Stacking is explicit (`z-*` classes).
  const droneKey = drones
    .map((drone) => `${drone.id}:${drone.status === 'IN_FLIGHT' ? 'flying' : 'away'}`)
    .join('|')

  useEffect(() => {
    const map = mapRef.current
    const elements = droneElementsRef.current
    const markerByDrone = droneMarkersRef.current
    if (status !== 'ready' || !map) return

    const markers = dronesRef.current.map((drone) => {
      const element = createDroneMarkerElement(drone, () => onSelectDroneRef.current?.(drone.id))
      elements.set(drone.id, element)
      const visual = flightsRef.current.find((flight) => flight.droneId === drone.id)
      const marker = new mapboxgl.Marker({
        element,
        offset: droneOffsetsRef.current.get(drone.id) ?? NO_PIXEL_OFFSET,
      })
        .setLngLat(visual ? [...visual.motion.position] : drone.coordinates)
        .addTo(map)
      markerByDrone.set(drone.id, marker)
      return marker
    })

    return () => {
      markers.forEach((marker) => marker.remove())
      elements.clear()
      markerByDrone.clear()
    }
  }, [droneKey, status])

  // In place: the accessible name and the position follow the latest backend snapshot. A flying
  // drone is drawn at its flight snapshot; the real stored coordinates are never changed.
  useEffect(() => {
    const visuals = new Map(flights.map((flight) => [flight.droneId, flight]))
    for (const drone of drones) {
      const element = droneElementsRef.current.get(drone.id)
      const marker = droneMarkersRef.current.get(drone.id)
      if (!element || !marker) continue
      element.setAttribute('aria-label', droneMarkerLabel(drone))
      const visual = visuals.get(drone.id)
      marker.setLngLat(visual ? [...visual.motion.position] : drone.coordinates)
    }
  }, [drones, flights, status, droneKey])

  // Smooth motion between two snapshots: only the picture, never the mission. Each frame moves
  // the marker from the snapshot toward the backend's target, never past it; the next snapshot
  // replaces it. Off for reduced motion and for a worker that stopped updating.
  useEffect(() => {
    if (status !== 'ready' || typeof requestAnimationFrame !== 'function') return
    const animated = flights.filter((flight) => flight.animate)
    if (animated.length === 0) return

    let frame = 0
    const step = () => {
      const now = performance.now()
      for (const visual of animated) {
        droneMarkersRef.current
          .get(visual.droneId)
          ?.setLngLat(interpolatePosition(visual.motion, (now - visual.receivedAt) / 1000))
      }
      frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [flights, status, droneKey])

  // Display only: shifts the marker on screen; the marker's coordinates stay the real ones.
  useEffect(() => {
    droneMarkersRef.current.forEach((marker, droneId) =>
      marker.setOffset(droneOffsets.get(droneId) ?? NO_PIXEL_OFFSET),
    )
  }, [drones, droneOffsets, status, droneKey])

  useEffect(() => {
    droneElementsRef.current.forEach((element, droneId) =>
      setDroneMarkerSelected(element, droneId === selectedDroneId),
    )
  }, [drones, status, selectedDroneId, droneKey])

  useEffect(() => {
    orderOffsetsRef.current = orderOffsets
  }, [orderOffsets])

  // Order markers are reconciled by order id: a new order gets a marker, an order that leaves the
  // active list (its delivered window ended) loses only its own, and every other marker keeps its
  // element, its keyboard focus and its place. A status change is handled in place, below. Orders
  // that failed to load are never passed in, so no stale destination is shown as current.
  const orderKey = orders.map((order) => order.id).join('|')

  // Declared first so it runs first when the map becomes (un)available: it clears every marker on
  // unmount or when the map is not ready, and the reconcile below then starts from nothing.
  useEffect(() => {
    const elements = orderElementsRef.current
    const markerByOrder = orderMarkersRef.current
    return () => {
      markerByOrder.forEach((marker) => marker.remove())
      elements.clear()
      markerByOrder.clear()
    }
  }, [status])

  useEffect(() => {
    const map = mapRef.current
    const elements = orderElementsRef.current
    const markerByOrder = orderMarkersRef.current
    if (status !== 'ready' || !map) return

    const present = new Set(ordersRef.current.map((order) => order.id))
    markerByOrder.forEach((marker, id) => {
      if (present.has(id)) return
      marker.remove()
      markerByOrder.delete(id)
      elements.delete(id)
    })
    for (const order of ordersRef.current) {
      if (markerByOrder.has(order.id)) continue
      const element = createOrderMarkerElement(order, () => onSelectOrderRef.current?.(order.id))
      elements.set(order.id, element)
      markerByOrder.set(
        order.id,
        new mapboxgl.Marker({
          element,
          offset: orderOffsetsRef.current.get(order.id) ?? NO_PIXEL_OFFSET,
        })
          .setLngLat(order.coordinates)
          .addTo(map),
      )
    }
  }, [orderKey, status])

  // In place: colour, state and accessible name follow the latest status; the position follows an
  // edited destination.
  useEffect(() => {
    for (const order of orders) {
      const element = orderElementsRef.current.get(order.id)
      if (!element) continue
      updateOrderMarkerElement(element, order)
      orderMarkersRef.current.get(order.id)?.setLngLat(order.coordinates)
    }
  }, [orders, status, orderKey])

  // Display only: shifts the marker on screen; the marker's coordinates stay the real ones.
  useEffect(() => {
    orderMarkersRef.current.forEach((marker, orderId) =>
      marker.setOffset(orderOffsets.get(orderId) ?? NO_PIXEL_OFFSET),
    )
  }, [orders, orderOffsets, status, orderKey])

  useEffect(() => {
    orderElementsRef.current.forEach((element, orderId) =>
      setOrderMarkerSelected(element, orderId === selectedOrderId),
    )
  }, [orders, status, selectedOrderId, orderKey])

  useEffect(() => {
    const container = containerRef.current
    if (!token || !container) return

    let map: mapboxgl.Map
    try {
      map = new mapboxgl.Map({
        accessToken: token,
        container,
        style: MAP_STYLE,
        bounds: TRICITY_BOUNDS,
        fitBoundsOptions: { padding: TRICITY_FIT_PADDING_PX },
      })
    } catch {
      // Deferred so the state update is not a synchronous setState inside the effect body.
      queueMicrotask(() => setStatus('error'))
      return
    }

    mapRef.current = map

    let hasLoaded = false
    map.on('load', () => {
      hasLoaded = true
      setStatus('ready')
    })
    // Errors before the first load (bad token, style failure) are fatal. Later errors, such as a
    // single failed tile, must not hide a working map.
    map.on('error', () => {
      if (!hasLoaded) setStatus('error')
    })

    // Mapbox only listens to window resizes; the workspace can also change size on its own.
    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      mapRef.current = null
      map.remove()
    }
  }, [token])

  if (!token) {
    return (
      <MapMessage role="alert">
        <p className="font-medium text-fg">Map unavailable</p>
        <p className="mt-1">
          Set <code className="font-mono">VITE_MAPBOX_TOKEN</code> in{' '}
          <code className="font-mono">frontend/.env.local</code> and restart the dev server.
        </p>
      </MapMessage>
    )
  }

  return (
    <div className="absolute inset-0">
      {/* size-full, not absolute: mapbox-gl.css (unlayered) forces position: relative on this
          element and would override Tailwind's layered `absolute`, collapsing the height to 0. */}
      <div ref={containerRef} className="size-full" />
      {status === 'loading' && <MapMessage role="status">Loading map…</MapMessage>}
      {status === 'error' && (
        <MapMessage role="alert">
          <p className="font-medium text-fg">Map failed to load</p>
          <p className="mt-1">
            Check that your Mapbox token is valid and allowed for this site, then reload.
          </p>
        </MapMessage>
      )}
    </div>
  )
}
