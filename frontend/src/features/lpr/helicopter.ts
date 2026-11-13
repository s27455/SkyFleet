import type { GeoJSONSource } from 'mapbox-gl'

import type { LprScenario } from '../../types/lpr'

const METRES_PER_DEGREE = 111_320

/** What the map's GeoJSON source accepts (the types of the map library, not a second copy). */
export type ZoneData = Parameters<GeoJSONSource['setData']>[0]

type Position = [longitude: number, latitude: number]

/** Metres east and north of `origin`, with longitude scaled by the cosine of the latitude. */
function toMetres(origin: Position, point: Position): [number, number] {
  const scale = Math.cos((origin[1] * Math.PI) / 180)
  return [
    (point[0] - origin[0]) * scale * METRES_PER_DEGREE,
    (point[1] - origin[1]) * METRES_PER_DEGREE,
  ]
}

/**
 * Where to draw the helicopter `secondsSinceReceived` after the backend answered.
 *
 * This only smooths the picture: the helicopter flies a straight route at a constant speed, so the
 * marker moves from the answered position along the route at the scenario's speed and stops at the
 * end. The next answer replaces whatever is drawn here; nothing is decided from it.
 */
export function helicopterPosition(scenario: LprScenario, secondsSinceReceived: number): Position {
  const { routeStart: start, routeEnd: end, position, speedMs } = scenario
  const [endX, endY] = toMetres(start, end)
  const length = Math.hypot(endX, endY)
  if (length === 0) return [position[0], position[1]]
  const [x, y] = toMetres(start, position)
  const done = Math.min(Math.max((x * endX + y * endY) / (length * length), 0), 1)
  const fraction = Math.min(done + (speedMs * Math.max(secondsSinceReceived, 0)) / length, 1)
  return [start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction]
}

/** The safety zone as a GeoJSON polygon: a circle of `radiusM` metres around the helicopter. */
export function zoneFeature(center: Position, radiusM: number, steps = 64): ZoneData {
  const scale = Math.cos((center[1] * Math.PI) / 180)
  const ring: [number, number][] = []
  for (let step = 0; step <= steps; step += 1) {
    const angle = (2 * Math.PI * (step % steps)) / steps
    ring.push([
      center[0] + (radiusM * Math.sin(angle)) / (METRES_PER_DEGREE * scale),
      center[1] + (radiusM * Math.cos(angle)) / METRES_PER_DEGREE,
    ])
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}
