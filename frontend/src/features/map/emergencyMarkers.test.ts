import { describe, expect, it, vi } from 'vitest'

import type { Drone } from '../../types/drone'
import type { EmergencyPoint } from '../flights/emergencyPoints'
import { droneMarkerLabel, setDroneMarkerEmergency, setDroneMarkerYielding } from './droneMarkers'
import { createEmergencyMarkerElement, emergencyMarkerLabel } from './emergencyMarkers'

const point = (level: EmergencyPoint['level']): EmergencyPoint => ({
  droneId: 'DRN-010',
  orderId: 'ORD-001',
  level,
  position: [18.6, 54.38],
})

const DRONE = {
  id: 'DRN-010',
  status: 'MAINTENANCE',
  batteryPct: 91,
  coordinates: [18.6, 54.38],
} as Drone

describe('emergency landing marker', () => {
  it('says in words whether the drone is landing or grounded', () => {
    expect(emergencyMarkerLabel(point('approach'))).toMatch(/is landing after a drone failure/)
    expect(emergencyMarkerLabel(point('grounded'))).toMatch(/grounded .* requires service/)
  })

  it('is a red, labelled button that selects its drone, and pulses only on the approach', () => {
    const onClick = vi.fn()
    const approach = createEmergencyMarkerElement(point('approach'), onClick)
    const grounded = createEmergencyMarkerElement(point('grounded'), vi.fn())

    approach.click()

    expect(onClick).toHaveBeenCalledTimes(1)
    expect(approach).toHaveClass('bg-status-critical', 'animate-pulse')
    expect(grounded).toHaveClass('bg-status-critical')
    expect(grounded).not.toHaveClass('animate-pulse')
    expect(approach.dataset.markerKind).toBe('emergency')
    expect(approach.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('failed drone marker', () => {
  it('adds the failure to the accessible name only when there is one', () => {
    expect(droneMarkerLabel(DRONE)).not.toMatch(/failure/)
    expect(droneMarkerLabel(DRONE, 'approach')).toMatch(/emergency landing in progress/)
    expect(droneMarkerLabel(DRONE, 'grounded')).toMatch(/grounded after a drone failure/)
  })

  it('shows and clears the red warning in place', () => {
    const element = document.createElement('button')

    setDroneMarkerEmergency(element, 'grounded')
    expect(element).toHaveClass('border-status-critical!', 'ring-status-critical')
    expect(element.dataset.emergency).toBe('grounded')

    setDroneMarkerEmergency(element, undefined)
    expect(element).not.toHaveClass('ring-status-critical')
    expect(element.dataset.emergency).toBeUndefined()
  })
})

describe('drone waiting for the LPR helicopter (Feature 018E)', () => {
  it('says so in the accessible name, and a failure still wins', () => {
    expect(droneMarkerLabel(DRONE, undefined, true)).toMatch(/waiting for the LPR helicopter/)
    expect(droneMarkerLabel(DRONE, undefined, false)).not.toMatch(/LPR/)
    expect(droneMarkerLabel(DRONE, 'approach', true)).not.toMatch(/LPR/)
  })

  it('shows and clears the amber outline in place', () => {
    const element = document.createElement('button')

    setDroneMarkerYielding(element, true)
    expect(element).toHaveClass('border-status-warning!', 'ring-status-warning')
    expect(element.dataset.yielding).toBe('lpr')

    setDroneMarkerYielding(element, false)
    expect(element).not.toHaveClass('ring-status-warning')
    expect(element.dataset.yielding).toBeUndefined()
  })
})
