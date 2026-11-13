import { describe, expect, it } from 'vitest'

import { createDroneMaterials, disposeMaterials, highlightFor, ledFor } from './droneMaterials'

describe('status materials', () => {
  const materials = createDroneMaterials()

  it('draws nominal parts green and without a highlight', () => {
    expect(ledFor(materials, 'nominal')).toBe(materials.ledOk)
    expect(highlightFor(materials, 'nominal')).toBeNull()
  })

  it('draws attention amber and critical red, each with its own ring and wash', () => {
    expect(ledFor(materials, 'attention')).toBe(materials.ledAmber)
    expect(ledFor(materials, 'critical')).toBe(materials.ledRed)
    expect(highlightFor(materials, 'attention')).toEqual({
      ring: materials.ringAmber,
      wash: materials.washAmber,
    })
    expect(highlightFor(materials, 'critical')).toEqual({
      ring: materials.ringRed,
      wash: materials.washRed,
    })
  })

  it('uses the status colours of the design tokens', () => {
    expect(materials.ringAmber.color.getHexString()).toBe('fbbf24')
    expect(materials.ringRed.color.getHexString()).toBe('f87171')
  })

  it('disposes every material, the new ones included', () => {
    const fresh = createDroneMaterials()
    let disposed = 0
    for (const material of Object.values(fresh))
      material.addEventListener('dispose', () => disposed++)

    disposeMaterials(fresh)

    expect(disposed).toBe(Object.keys(fresh).length)
  })
})
