import type { EmergencyPoint } from '../flights/emergencyPoints'

const SVG_NS = 'http://www.w3.org/2000/svg'

// A red disc with a cross: a warning that does not rely on colour alone. The pulse marks the active
// approach; a drone that already landed gets the same marker, steady.
const EMERGENCY_MARKER_CLASS =
  'z-10 flex size-7 cursor-pointer items-center justify-center rounded-full border-2 border-fg bg-status-critical text-canvas shadow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'
const APPROACH_CLASS = 'animate-pulse'

export function emergencyMarkerLabel(point: EmergencyPoint) {
  return point.level === 'approach'
    ? `Emergency landing point, drone ${point.droneId} is landing after a drone failure`
    : `Emergency landing point, drone ${point.droneId} is grounded after a drone failure and requires service`
}

function createCross() {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 24 24')
  svg.setAttribute('width', '14')
  svg.setAttribute('height', '14')
  svg.setAttribute('fill', 'none')
  svg.setAttribute('stroke', 'currentColor')
  svg.setAttribute('stroke-width', '3.5')
  svg.setAttribute('stroke-linecap', 'round')
  svg.setAttribute('aria-hidden', 'true')
  const path = document.createElementNS(SVG_NS, 'path')
  path.setAttribute('d', 'M6 6l12 12M18 6L6 18')
  svg.appendChild(path)
  return svg
}

/** Selecting the marker selects its drone, so the drone panel explains what happened. */
export function createEmergencyMarkerElement(point: EmergencyPoint, onClick: () => void) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = `${EMERGENCY_MARKER_CLASS} ${point.level === 'approach' ? APPROACH_CLASS : ''}`
  element.dataset.markerKind = 'emergency'
  element.dataset.level = point.level
  element.setAttribute('aria-label', emergencyMarkerLabel(point))
  element.appendChild(createCross())
  element.addEventListener('click', onClick)
  return element
}
