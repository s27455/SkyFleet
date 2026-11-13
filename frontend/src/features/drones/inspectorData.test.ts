import { describe, expect, it } from 'vitest'

import type { Flight } from '../../types/flight'
import type { Mission } from '../../types/mission'
import type { Order } from '../../types/order'
import { resolveInspectorData } from './inspectorData'

const FLIGHT: Flight = {
  missionId: 'MIS-1',
  orderId: 'ORD-1',
  droneId: 'DRN-1',
  missionStatus: 'IN_FLIGHT',
  phase: 'OUTBOUND',
  progress: 0.5,
  position: [18.5, 54.4],
  batteryPct: 80,
  target: null,
  originHubId: 'hub-a',
  plannedReturnHubId: 'hub-a',
  landingTargetHubId: 'hub-a',
  startedAt: '2026-11-12T10:00:00Z',
  deliveredAt: null,
  recalledAt: null,
  failedAt: null,
  recipientUnavailableAt: null,
  handoverFailedAt: null,
  updatedAt: '2026-11-12T10:00:01Z',
  snapshotAgeS: 1,
  emergency: null,
}

const MISSION: Mission = {
  id: 'MIS-1',
  orderId: 'ORD-1',
  droneId: 'DRN-1',
  originHubId: 'hub-a',
  returnHubId: 'hub-b',
  status: 'IN_FLIGHT',
  totalKm: 3.2,
}

const ORDER: Order = {
  id: 'ORD-1',
  originHubId: 'hub-a',
  destinationAddress: 'Długa 1, Gdańsk',
  coordinates: [18.65, 54.35],
  packageWeightKg: 1.8,
  status: 'OUT_FOR_DELIVERY',
  deliveredAt: null,
  cancelledAt: null,
  deliveryFailedAt: null,
  createdAt: '2026-11-12T09:00:00Z',
  updatedAt: '2026-11-12T10:00:00Z',
}

const READY = {
  droneId: 'DRN-1',
  flights: [FLIGHT],
  missions: [MISSION],
  orders: [ORDER],
  flightsStatus: 'ready' as const,
  missionsStatus: 'ready' as const,
  ordersStatus: 'ready' as const,
}

describe('resolveInspectorData', () => {
  it('finds the flight, its mission and the parcel being carried', () => {
    const data = resolveInspectorData(READY)

    expect(data.flight).toEqual({ kind: 'found', value: FLIGHT })
    expect(data.mission).toEqual({
      kind: 'found',
      value: { id: 'MIS-1', status: 'IN_FLIGHT', returnHubId: 'hub-b', totalKm: 3.2 },
    })
    expect(data.payload).toEqual({ kind: 'found', value: ORDER })
  })

  it('reports nothing for an idle drone once the data is known', () => {
    const data = resolveInspectorData({
      ...READY,
      droneId: 'DRN-9',
    })

    expect(data.flight).toEqual({ kind: 'none' })
    expect(data.mission).toEqual({ kind: 'none' })
    expect(data.payload).toEqual({ kind: 'none' })
  })

  it('shows an assigned mission and its parcel before the drone takes off', () => {
    const data = resolveInspectorData({
      ...READY,
      flights: [],
      missions: [{ ...MISSION, status: 'ASSIGNED' }],
    })

    expect(data.flight).toEqual({ kind: 'none' })
    expect(data.mission).toMatchObject({
      kind: 'found',
      value: { id: 'MIS-1', status: 'ASSIGNED' },
    })
    expect(data.payload).toEqual({ kind: 'found', value: ORDER })
  })

  it('ignores finished and cancelled missions', () => {
    const data = resolveInspectorData({
      ...READY,
      flights: [],
      missions: [
        { ...MISSION, id: 'MIS-OLD', status: 'COMPLETED' },
        { ...MISSION, id: 'MIS-OLD2', status: 'CANCELLED' },
      ],
    })

    expect(data.mission).toEqual({ kind: 'none' })
    expect(data.payload).toEqual({ kind: 'none' })
  })

  it('distinguishes loading and failed data from confirmed absence', () => {
    const loading = resolveInspectorData({
      ...READY,
      droneId: 'DRN-9',
      flightsStatus: 'loading',
      missionsStatus: 'loading',
      ordersStatus: 'loading',
    })
    expect(loading.flight).toEqual({ kind: 'unavailable', reason: 'loading' })
    expect(loading.mission).toEqual({ kind: 'unavailable', reason: 'loading' })
    expect(loading.payload).toEqual({ kind: 'unavailable', reason: 'loading' })

    const failed = resolveInspectorData({
      ...READY,
      droneId: 'DRN-9',
      flights: [],
      missions: [],
      orders: [],
      flightsStatus: 'error',
      missionsStatus: 'error',
    })
    expect(failed.flight).toEqual({ kind: 'unavailable', reason: 'error' })
    expect(failed.mission).toEqual({ kind: 'unavailable', reason: 'error' })
    expect(failed.payload).toEqual({ kind: 'unavailable', reason: 'error' })
  })

  it('still names the mission from the flight when the mission list cannot be read', () => {
    const data = resolveInspectorData({ ...READY, missions: [], missionsStatus: 'error' })

    expect(data.mission).toEqual({ kind: 'found', value: { id: 'MIS-1', status: 'IN_FLIGHT' } })
  })

  it('does not invent a payload when the order is unreadable or missing', () => {
    expect(resolveInspectorData({ ...READY, orders: [], ordersStatus: 'error' }).payload).toEqual({
      kind: 'unavailable',
      reason: 'error',
    })
    expect(resolveInspectorData({ ...READY, orders: [] }).payload).toEqual({
      kind: 'unavailable',
      reason: 'missing',
    })
  })
})
