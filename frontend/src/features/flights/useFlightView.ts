import { useMemo } from 'react'

import type { Drone } from '../../types/drone'
import type { Flight } from '../../types/flight'
import type { LprScenario } from '../../types/lpr'
import type { LprView } from '../map/MapView'
import {
  droneEmergencies as deriveDroneEmergencies,
  emergencyPoints as deriveEmergencyPoints,
  interruptedOrderIds as deriveInterruptedOrderIds,
} from './emergencyPoints'
import {
  canAnimateFlights,
  flightsByDrone,
  isActiveFlight,
  isFailable,
  isRecipientTargetable,
} from './flightStatus'
import type { FlightVisual } from './interpolation'
import { usePrefersReducedMotion } from './usePrefersReducedMotion'

interface FlightViewInput {
  drones: readonly Drone[]
  flights: readonly Flight[]
  /** The worker has not updated the flights recently. */
  workerStale: boolean
  /** `performance.now()` when the flights last arrived; null before the first answer. */
  flightsReceivedAt: number | null
  /** The latest flights refresh failed and older data is shown. */
  flightsStale: boolean
  /** The LPR helicopter as the backend reports it (null scenario: none running). */
  lpr: { scenario: LprScenario | null; receivedAt: number | null; stale: boolean }
}

/**
 * What the map and the incident controls need from the backend's flights: the animated flight
 * visuals, drone emergencies, interrupted orders, the LPR helicopter view and the waiting drones.
 * Everything is derived from the data it is given; nothing is fetched here.
 */
export function useFlightView({
  drones,
  flights,
  workerStale,
  flightsReceivedAt,
  flightsStale,
  lpr,
}: FlightViewInput) {
  const reducedMotion = usePrefersReducedMotion()

  // Flights: the backend's snapshots. The map only glides between them (and not at all for reduced
  // motion or a worker that stopped updating); phase, battery and landing come from the backend.
  const flightByDrone = useMemo(() => flightsByDrone(flights), [flights])
  // Drone failures (Feature 018C), all derived from the backend's flights and drones.
  const emergencyPoints = useMemo(() => deriveEmergencyPoints(flights, drones), [flights, drones])
  const droneEmergencies = useMemo(() => deriveDroneEmergencies(emergencyPoints), [emergencyPoints])
  const interruptedOrderIds = useMemo(() => deriveInterruptedOrderIds(flights), [flights])
  const canFailDrone = useMemo(() => flights.some(isFailable), [flights])
  const canMarkRecipient = useMemo(() => flights.some(isRecipientTargetable), [flights])

  // The LPR helicopter (Feature 018E): the backend's scenario and which drones wait for it.
  const { scenario: lprScenario, receivedAt: lprReceivedAt, stale: lprStale } = lpr
  const lprView = useMemo<LprView | null>(
    () =>
      lprScenario === null || lprReceivedAt === null
        ? null
        : {
            scenario: lprScenario,
            receivedAt: lprReceivedAt,
            animate: canAnimateFlights({
              reducedMotion,
              workerStale: false, // the helicopter is computed from the clock, not by the worker
              refreshFailed: lprStale,
            }),
          },
    [lprScenario, lprReceivedAt, reducedMotion, lprStale],
  )
  const yieldingDroneIds = useMemo(
    () => new Set(flights.filter((flight) => flight.yieldingToLpr).map((flight) => flight.droneId)),
    [flights],
  )

  const flightVisuals = useMemo<FlightVisual[]>(
    () =>
      flightsReceivedAt === null
        ? []
        : flights.filter(isActiveFlight).map((flight) => ({
            droneId: flight.droneId,
            motion: {
              position: flight.position,
              target: flight.target,
              snapshotAgeS: flight.snapshotAgeS,
            },
            receivedAt: flightsReceivedAt,
            animate: canAnimateFlights({
              reducedMotion,
              workerStale,
              refreshFailed: flightsStale,
            }),
          })),
    [flights, flightsReceivedAt, reducedMotion, workerStale, flightsStale],
  )

  return {
    flightByDrone,
    emergencyPoints,
    droneEmergencies,
    interruptedOrderIds,
    canFailDrone,
    canMarkRecipient,
    lprView,
    yieldingDroneIds,
    flightVisuals,
  }
}
