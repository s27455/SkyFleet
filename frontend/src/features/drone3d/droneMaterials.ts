import {
  Color,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  type Material,
} from 'three'

/** Brand accent (the `accent` design token) used for the LED details. */
const ACCENT = '#22d3ee'

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

export function disposeMaterials(materials: Record<string, Material>): void {
  for (const material of Object.values(materials)) material.dispose()
}
