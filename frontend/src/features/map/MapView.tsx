import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { type ReactNode, useEffect, useRef, useState } from 'react'

import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { type PixelOffset, createDroneMarkerElement, setDroneMarkerSelected } from './droneMarkers'
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
  /** Screen-space offsets (px) by drone id for drones sharing a location. Display only. */
  droneOffsets?: ReadonlyMap<string, PixelOffset>
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
}: MapViewProps) {
  const token = getMapboxToken()
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const markerElementsRef = useRef(new Map<string, HTMLElement>())
  const droneElementsRef = useRef(new Map<string, HTMLElement>())
  const droneMarkersRef = useRef(new Map<string, mapboxgl.Marker>())
  const droneOffsetsRef = useRef(droneOffsets)
  const onSelectHubRef = useRef(onSelectHub)
  const onSelectDroneRef = useRef(onSelectDrone)
  const [status, setStatus] = useState<MapStatus>('loading')

  useEffect(() => {
    onSelectHubRef.current = onSelectHub
  }, [onSelectHub])

  useEffect(() => {
    onSelectDroneRef.current = onSelectDrone
  }, [onSelectDrone])

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

  // Drone markers are rebuilt only when the drones themselves change, never on selection and
  // never because display offsets changed (that would drop keyboard focus, e.g. when the Hubs load
  // after the drones). Offsets are applied to the existing markers in the effect below. Stacking
  // is explicit (`z-*` classes on the elements), not left to DOM order.
  useEffect(() => {
    const map = mapRef.current
    const elements = droneElementsRef.current
    const markerByDrone = droneMarkersRef.current
    if (status !== 'ready' || !map) return

    const markers = drones.map((drone) => {
      const element = createDroneMarkerElement(drone, () => onSelectDroneRef.current?.(drone.id))
      elements.set(drone.id, element)
      const marker = new mapboxgl.Marker({
        element,
        offset: droneOffsetsRef.current.get(drone.id) ?? NO_PIXEL_OFFSET,
      })
        .setLngLat(drone.coordinates)
        .addTo(map)
      markerByDrone.set(drone.id, marker)
      return marker
    })

    return () => {
      markers.forEach((marker) => marker.remove())
      elements.clear()
      markerByDrone.clear()
    }
  }, [drones, status])

  // Display only: shifts the marker on screen; the marker's coordinates stay the real ones.
  useEffect(() => {
    droneMarkersRef.current.forEach((marker, droneId) =>
      marker.setOffset(droneOffsets.get(droneId) ?? NO_PIXEL_OFFSET),
    )
  }, [drones, droneOffsets, status])

  useEffect(() => {
    droneElementsRef.current.forEach((element, droneId) =>
      setDroneMarkerSelected(element, droneId === selectedDroneId),
    )
  }, [drones, status, selectedDroneId])

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
