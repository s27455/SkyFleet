import type { Flight } from '../../types/flight'
import type { Mission } from '../../types/mission'
import type { Order } from '../../types/order'

/** How a backend resource is doing: the three states of `ResourceState`. */
export type DataStatus = 'loading' | 'ready' | 'error'

/**
 * What the inspector can say about one thing. "Unavailable" means the data could not be read (still
 * loading, or the request failed), which is different from "none", which the backend confirmed.
 */
export type Lookup<T> =
  | { kind: 'unavailable'; reason: 'loading' | 'error' | 'missing' }
  | { kind: 'none' }
  | { kind: 'found'; value: T }

/** A mission as far as it is known: a flight alone knows its id and status, not its distance. */
export interface InspectedMission {
  id: string
  status: string
  /** Planned return Hub id and total route length; only known from the mission list. */
  returnHubId?: string
  totalKm?: number
}

export interface InspectorData {
  flight: Lookup<Flight>
  mission: Lookup<InspectedMission>
  /** The order the drone is carrying or has been assigned: its weight is the current payload. */
  payload: Lookup<Order>
}

interface InspectorSources {
  droneId: string
  flights: readonly Flight[]
  missions: readonly Mission[]
  orders: readonly Order[]
  flightsStatus: DataStatus
  missionsStatus: DataStatus
  ordersStatus: DataStatus
}

const unavailable = (status: DataStatus): Lookup<never> => ({
  kind: 'unavailable',
  reason: status === 'error' ? 'error' : 'loading',
})

/** Mission states in which a drone still has a mission to show when no flight is reported. */
const OPEN_MISSION_STATUSES: readonly string[] = ['ASSIGNED', 'IN_FLIGHT']

/**
 * Resolves the drone's flight, mission and payload from data the app already polls. Nothing is
 * guessed: a value is only "found" when a backend record says so.
 */
export function resolveInspectorData(sources: InspectorSources): InspectorData {
  const { droneId, flights, missions, orders } = sources

  const flightRecord = flights.find((flight) => flight.droneId === droneId)
  const flight: Lookup<Flight> =
    sources.flightsStatus !== 'ready'
      ? unavailable(sources.flightsStatus)
      : flightRecord
        ? { kind: 'found', value: flightRecord }
        : { kind: 'none' }

  const missionRecord =
    sources.missionsStatus === 'ready'
      ? (missions.find((mission) => mission.id === flightRecord?.missionId) ??
        missions.find(
          (mission) =>
            mission.droneId === droneId && OPEN_MISSION_STATUSES.includes(mission.status),
        ))
      : undefined

  let mission: Lookup<InspectedMission>
  if (missionRecord) {
    mission = {
      kind: 'found',
      value: {
        id: missionRecord.id,
        status: missionRecord.status,
        returnHubId: missionRecord.returnHubId,
        totalKm: missionRecord.totalKm,
      },
    }
  } else if (flightRecord) {
    // The flight names its mission even when the mission list is not available (yet).
    mission = {
      kind: 'found',
      value: { id: flightRecord.missionId, status: flightRecord.missionStatus },
    }
  } else if (sources.missionsStatus !== 'ready') {
    mission = unavailable(sources.missionsStatus)
  } else {
    mission = { kind: 'none' }
  }

  const orderId = flightRecord?.orderId ?? missionRecord?.orderId
  let payload: Lookup<Order>
  if (orderId === undefined || orderId === null) {
    // No mission, no payload; but if missions could not be read we cannot tell.
    payload = mission.kind === 'unavailable' ? mission : { kind: 'none' }
  } else if (sources.ordersStatus !== 'ready') {
    payload = unavailable(sources.ordersStatus)
  } else {
    const order = orders.find((candidate) => candidate.id === orderId)
    // The order list is readable but has no such order (for example it was just removed).
    payload = order ? { kind: 'found', value: order } : { kind: 'unavailable', reason: 'missing' }
  }

  return { flight, mission, payload }
}
