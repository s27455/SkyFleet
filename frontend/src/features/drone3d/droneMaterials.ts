import {
  Color,
  DoubleSide,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  type Material,
} from 'three'

import type { PartLevel } from './droneParts'

/** Brand accent (the `accent` design token) used for the LED details. */
const ACCENT = '#22d3ee'
/** The `status-warning` and `status-critical` design tokens, for the health highlights. */
const AMBER = '#fbbf24'
const RED = '#f87171'

const halo = (color: string, opacity: number) =>
  new MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthWrite: false,
    side: DoubleSide,
    toneMapped: false,
  })

const emissive = (base: string, glow: string, intensity: number) =>
  new MeshStandardMaterial({
    color: new Color(base),
    emissive: new Color(glow),
    emissiveIntensity: intensity,
    roughness: 0.4,
  })

/** One shared set of materials for the whole model; created once per viewer, disposed on unmount. */
export function createDroneMaterials() {
  return {
    shell: new MeshPhysicalMaterial({
      color: '#dfe5ec',
      roughness: 0.38,
      metalness: 0.1,
      clearcoat: 1,
      clearcoatRoughness: 0.2,
    }),
    carbon: new MeshStandardMaterial({ color: '#1c2128', roughness: 0.45, metalness: 0.55 }),
    graphite: new MeshStandardMaterial({ color: '#2a313b', roughness: 0.5, metalness: 0.4 }),
    metal: new MeshStandardMaterial({ color: '#9aa4b2', roughness: 0.35, metalness: 1 }),
    motorMetal: new MeshStandardMaterial({ color: '#3e4753', roughness: 0.3, metalness: 0.9 }),
    rubber: new MeshStandardMaterial({ color: '#14171b', roughness: 0.9, metalness: 0 }),
    sensor: new MeshPhysicalMaterial({
      color: '#07090c',
      roughness: 0.1,
      metalness: 0.6,
      clearcoat: 1,
    }),
    blade: new MeshStandardMaterial({ color: '#232a33', roughness: 0.4, metalness: 0.25 }),
    ledAccent: emissive('#0b2a30', ACCENT, 1.8),
    ledOk: emissive('#08241a', '#34d399', 1.6),
    ledAmber: emissive('#2e2204', AMBER, 2.2),
    ledRed: emissive('#2e0d0d', RED, 2.4),
    // Health highlights: a ring and a translucent wash per level, and the selection outline.
    ringAmber: halo(AMBER, 0.95),
    ringRed: halo(RED, 0.95),
    washAmber: halo(AMBER, 0.28),
    washRed: halo(RED, 0.32),
    selection: halo(ACCENT, 0.9),
    glass: new MeshStandardMaterial({
      color: '#9fd8e8',
      roughness: 0.05,
      metalness: 0,
      transparent: true,
      opacity: 0.16,
      depthWrite: false,
    }),
    parcel: new MeshStandardMaterial({ color: '#b98b57', roughness: 0.8, metalness: 0 }),
    tape: new MeshStandardMaterial({ color: '#d8c39a', roughness: 0.7, metalness: 0 }),
    // Faint swept-disc hint, shown only while the propellers spin.
    disc: new MeshBasicMaterial({
      color: ACCENT,
      transparent: true,
      opacity: 0.07,
      depthWrite: false,
    }),
  }
}

export type DroneMaterials = ReturnType<typeof createDroneMaterials>

/** The status LED material of a part: green when nominal, amber or red otherwise. */
export function ledFor(materials: DroneMaterials, level: PartLevel) {
  return level === 'critical'
    ? materials.ledRed
    : level === 'attention'
      ? materials.ledAmber
      : materials.ledOk
}

/** Ring and wash materials of a non-nominal level (nominal parts get no highlight). */
export function highlightFor(materials: DroneMaterials, level: PartLevel) {
  if (level === 'nominal') return null
  return level === 'critical'
    ? { ring: materials.ringRed, wash: materials.washRed }
    : { ring: materials.ringAmber, wash: materials.washAmber }
}

export function disposeMaterials(materials: Record<string, Material>): void {
  for (const material of Object.values(materials)) material.dispose()
}
