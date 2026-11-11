import type { Drone } from '../../types/drone'
import type { Hub } from '../../types/hub'
import { DRONE_STATUS_DISPLAY } from '../drones/droneStatus'

export type PixelOffset = [x: number, y: number]

const HUB_MARKER_SIZE_PX = 40
// 24px is the WCAG 2.2 minimum pointer-target size; the glyph inside is only 12px.
const DRONE_MARKER_SIZE_PX = 24
const RING_GAP_PX = 8
// Keeps ring markers clear of a Hub marker sitting at the true point in the middle.
const MIN_RING_RADIUS_PX = HUB_MARKER_SIZE_PX / 2 + DRONE_MARKER_SIZE_PX / 2 + RING_GAP_PX

// Limitation: drones are grouped only when their coordinates are exactly equal (true for the seeded
// snapshot at a Hub). Nearby-but-different positions are not spread; moving drones would need
// pixel-distance clustering, which is out of scope for this feature.
const coordinateKey = ([lng, lat]: readonly [number, number]) => `${lng},${lat}`

/**
 * Screen-space (pixel) offsets that keep drones sharing a location individually visible.
 *
 * Display only: the drone's real coordinates are never changed. Drones that share a point with
 * another drone or with a Hub are spread on a ring around that point, in drone-id order, so the
 * result is deterministic. A drone alone at its location gets no entry (no offset).
 */
export function computeDroneOffsets(
  drones: readonly Drone[],
  hubs: readonly Hub[],
): ReadonlyMap<string, PixelOffset> {
  const hubPoints = new Set(hubs.map((hub) => coordinateKey(hub.coordinates)))
  const groups = new Map<string, Drone[]>()
  for (const drone of drones) {
    const key = coordinateKey(drone.coordinates)
    groups.set(key, [...(groups.get(key) ?? []), drone])
  }

  const offsets = new Map<string, PixelOffset>()
  for (const [key, group] of groups) {
    if (group.length === 1 && !hubPoints.has(key)) continue

    const sorted = [...group].sort((a, b) => a.id.localeCompare(b.id))
    const radius = Math.max(
      MIN_RING_RADIUS_PX,
      Math.ceil(((DRONE_MARKER_SIZE_PX + RING_GAP_PX) * sorted.length) / (2 * Math.PI)),
    )
    sorted.forEach((drone, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / sorted.length // first drone at the top
      offsets.set(drone.id, [
        Math.round(radius * Math.cos(angle)),
        Math.round(radius * Math.sin(angle)),
      ])
    })
  }
  return offsets
}

const DRONE_MARKER_CLASS =
  'z-20 flex size-6 items-center justify-center rounded-full border shadow cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'
// A non-flying drone away from every Hub is a flagged exception: dashed border, not just colour.
const DRONE_MARKER_AWAY_CLASS = 'border-dashed border-fg'
const DRONE_MARKER_FLIGHT_CLASS = 'border-fg'
const DRONE_MARKER_IDLE_CLASSES = ['bg-surface-raised', 'text-fg']
// The ring is a second, non-colour selection cue.
const DRONE_MARKER_SELECTED_CLASSES = ['bg-accent', 'text-canvas', 'ring-4', 'ring-accent/40']

const SVG_NS = 'http://www.w3.org/2000/svg'

/** A six-arm rotor glyph (the SF-1 is a hexacopter); decorative, the button carries the name. */
function createRotorGlyph() {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 24 24')
  svg.setAttribute('width', '12')
  svg.setAttribute('height', '12')
  svg.setAttribute('fill', 'none')
  svg.setAttribute('stroke', 'currentColor')
  svg.setAttribute('stroke-width', '2')
  svg.setAttribute('stroke-linecap', 'round')
  svg.setAttribute('aria-hidden', 'true')

  const tips = Array.from({ length: 6 }, (_, index) => {
    const angle = (Math.PI / 3) * index
    return [12 + 8 * Math.cos(angle), 12 + 8 * Math.sin(angle)] as const
  })
  const arms = document.createElementNS(SVG_NS, 'path')
  arms.setAttribute('d', tips.map(([x, y]) => `M12 12L${x.toFixed(2)} ${y.toFixed(2)}`).join(''))
  svg.appendChild(arms)
  tips.forEach(([x, y]) => {
    const rotor = document.createElementNS(SVG_NS, 'circle')
    rotor.setAttribute('cx', x.toFixed(2))
    rotor.setAttribute('cy', y.toFixed(2))
    rotor.setAttribute('r', '2')
    svg.appendChild(rotor)
  })
  return svg
}

/** Individual markers are for IN_FLIGHT drones; any other status here is a drone away from a Hub. */
const isAwayFromHub = (drone: Drone) => drone.status !== 'IN_FLIGHT'

export function droneMarkerLabel(drone: Drone) {
  const base = `Drone ${drone.id}, ${DRONE_STATUS_DISPLAY[drone.status].label}, battery ${drone.batteryPct}%`
  return isAwayFromHub(drone) ? `${base}, not at a Hub` : base
}

export function createDroneMarkerElement(drone: Drone, onClick: () => void) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = `${DRONE_MARKER_CLASS} ${
    isAwayFromHub(drone) ? DRONE_MARKER_AWAY_CLASS : DRONE_MARKER_FLIGHT_CLASS
  }`
  element.dataset.markerKind = 'drone'
  element.dataset.placement = isAwayFromHub(drone) ? 'away' : 'in-flight'
  element.setAttribute('aria-label', droneMarkerLabel(drone))
  element.appendChild(createRotorGlyph())
  element.addEventListener('click', onClick)
  setDroneMarkerSelected(element, false)
  return element
}

/** Updates the existing element in place so keyboard focus survives a selection change. */
export function setDroneMarkerSelected(element: HTMLElement, selected: boolean) {
  element.classList.remove(
    ...(selected ? DRONE_MARKER_IDLE_CLASSES : DRONE_MARKER_SELECTED_CLASSES),
  )
  element.classList.add(...(selected ? DRONE_MARKER_SELECTED_CLASSES : DRONE_MARKER_IDLE_CLASSES))
  element.setAttribute('aria-pressed', String(selected))
}
