import type { LngLatBoundsLike } from 'mapbox-gl'

export const MAP_STYLE = 'mapbox://styles/mapbox/dark-v11'

/** South-west and north-east corners [lng, lat] framing Gdynia, Sopot and Gdańsk. */
export const TRICITY_BOUNDS: LngLatBoundsLike = [
  [18.38, 54.27],
  [18.8, 54.62],
]

export const TRICITY_FIT_PADDING_PX = 24

/**
 * Credit for the official address data behind the generated delivery destinations (Feature 021E).
 * It is added to Mapbox's own attribution control, so it sits with the other map credits and is
 * never shown twice.
 */
export const DATA_ATTRIBUTION = 'Źródło: PRG, GUGiK (geoportal.gov.pl)'

/** Read at call time (not import time) so tests can stub the environment. */
export function getMapboxToken(): string | undefined {
  const token = import.meta.env.VITE_MAPBOX_TOKEN?.trim()
  return token ? token : undefined
}
