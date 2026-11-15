import { useCallback, useEffect, useRef, useState } from 'react'

import { startMission } from '../../api/missions'
import type { Flight } from '../../types/flight'
import { isActiveFlight } from '../flights/flightStatus'

interface RefreshActionsInput {
  flights: readonly Flight[]
  /** The `refresh` of each polled resource; each must be a stable reference. */
  refresh: {
    drones: () => void
    orders: () => void
    flights: () => void
    lpr: () => void
    missions: () => void
    rainWarning: () => void
  }
}

/**
 * Reads the affected resources at once after an operator action or a takeoff/landing, instead of
 * waiting for the next poll. It starts no polling and fetches nothing itself except the Start
 * Mission request. `activityTick` changes with each action so the Activity timelines re-read.
 */
export function useRefreshActions({ flights, refresh }: RefreshActionsInput) {
  const {
    drones: refreshDrones,
    orders: refreshOrders,
    flights: refreshFlights,
    lpr: refreshLpr,
    missions: refreshMissions,
    rainWarning: refreshRainWarning,
  } = refresh
  const [activityTick, setActivityTick] = useState(0)
  const refreshAfterIncident = useCallback(() => {
    setActivityTick((tick) => tick + 1) // the Activity timeline re-reads at once
    // A cancellation can recall a flying drone and cancel an assigned mission.
    refreshOrders()
    refreshMissions()
    refreshDrones()
    refreshFlights()
    refreshLpr()
    refreshRainWarning()
  }, [
    refreshOrders,
    refreshMissions,
    refreshDrones,
    refreshFlights,
    refreshLpr,
    refreshRainWarning,
  ])
  // A relocation changes the drone, its flight and its Activity; read them at once (Feature 019A).
  const refreshAfterRelocation = useCallback(() => {
    setActivityTick((tick) => tick + 1)
    refreshMissions()
    refreshDrones()
    refreshFlights()
  }, [refreshMissions, refreshDrones, refreshFlights])
  const startAssignedMission = useCallback(
    async (missionId: string) => {
      try {
        await startMission(missionId)
      } finally {
        // Show the outcome now instead of waiting for the next poll, whatever it was: a refused
        // or unreadable answer may still mean the state changed.
        refreshMissions()
        refreshDrones()
        refreshOrders()
        refreshFlights()
      }
    },
    [refreshMissions, refreshDrones, refreshOrders, refreshFlights],
  )

  // A takeoff or a landing changes drones, orders and missions together. When the set of flying
  // missions changes, read them at once so markers, Hub counts and statuses agree with the flights.
  const flyingKey = flights
    .filter(isActiveFlight)
    .map((flight) => flight.missionId)
    .sort()
    .join('|')
  const previousFlyingKey = useRef<string | null>(null)
  useEffect(() => {
    if (previousFlyingKey.current !== null && previousFlyingKey.current !== flyingKey) {
      refreshDrones()
      refreshOrders()
      refreshMissions()
    }
    previousFlyingKey.current = flyingKey
  }, [flyingKey, refreshDrones, refreshOrders, refreshMissions])

  return { activityTick, refreshAfterIncident, refreshAfterRelocation, startAssignedMission }
}
