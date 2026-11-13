import type { LprScenario } from '../../types/lpr'

const SVG_NS = 'http://www.w3.org/2000/svg'

// An amber disc with a helicopter: the same amber as the "yielding" label of the drones it stops.
const HELICOPTER_MARKER_CLASS =
  'z-15 flex size-8 items-center justify-center rounded-full border-2 border-fg bg-status-warning text-canvas shadow'

export const LPR_ZONE_COLOR = '#fbbf24'

export function helicopterLabel(scenario: LprScenario) {
  return `LPR helicopter in transit, safety zone of ${Math.round(scenario.radiusM)} m radius; delivery drones in its way wait`
}

function createIcon() {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 24 24')
  svg.setAttribute('width', '18')
  svg.setAttribute('height', '18')
  svg.setAttribute('fill', 'none')
  svg.setAttribute('stroke', 'currentColor')
  svg.setAttribute('stroke-width', '2')
  svg.setAttribute('stroke-linecap', 'round')
  svg.setAttribute('stroke-linejoin', 'round')
  svg.setAttribute('aria-hidden', 'true')
  const path = document.createElementNS(SVG_NS, 'path')
  path.setAttribute(
    'd',
    'M4 5h16M12 5v3M7 12a5 4 0 0 1 5-4h1a4 4 0 0 1 4 4v1a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2zM17 11h5M6 19h12M9 15v4M15 15v4',
  )
  svg.appendChild(path)
  return svg
}

/** A static, labelled image: the helicopter is information, not a control. */
export function createHelicopterMarkerElement(scenario: LprScenario) {
  const element = document.createElement('div')
  element.className = HELICOPTER_MARKER_CLASS
  element.dataset.markerKind = 'lpr-helicopter'
  element.setAttribute('role', 'img')
  element.setAttribute('aria-label', helicopterLabel(scenario))
  element.appendChild(createIcon())
  return element
}
