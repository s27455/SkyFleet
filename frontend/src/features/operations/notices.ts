import type { Flight } from '../../types/flight'

export type NoticeTone = 'critical' | 'warning' | 'info'

export interface OperationalNotice {
  id: string
  tone: NoticeTone
  text: string
}

export interface NoticeInput {
  /** Flights that ended in a simulated emergency (the backend's `emergency` field). */
  emergencies: readonly Flight[]
  rainWarningActive: boolean
  lprActive: boolean
  flightsUnavailable: boolean
  flightsStale: boolean
  fleetStale: boolean
  /** The worker stopped updating while flights are in the air. */
  workerStoppedWhileFlying: boolean
}

/**
 * The operational alerts the UI currently knows about, one short line each, derived from the same
 * data as the always-visible banners and notices. It is a summary of what is happening now, not a
 * history: past events are not part of it.
 */
export function buildNotices(input: NoticeInput): OperationalNotice[] {
  const notices: OperationalNotice[] = input.emergencies.map((flight) => ({
    id: `emergency-${flight.missionId}`,
    tone: 'critical',
    text: `Emergency: ${flight.droneId} (${flight.missionId}) is out of service`,
  }))
  if (input.rainWarningActive) {
    notices.push({
      id: 'rain',
      tone: 'warning',
      text: 'Rain warning active: new takeoffs are suspended',
    })
  }
  if (input.lprActive) {
    notices.push({ id: 'lpr', tone: 'warning', text: 'LPR helicopter is crossing the area' })
  }
  if (input.workerStoppedWhileFlying) {
    notices.push({
      id: 'worker',
      tone: 'warning',
      text: 'The simulation worker stopped updating flights',
    })
  }
  if (input.flightsUnavailable) {
    notices.push({ id: 'flights', tone: 'warning', text: 'Live flight data is unavailable' })
  } else if (input.flightsStale) {
    notices.push({ id: 'flights', tone: 'info', text: 'Live flight data could not be refreshed' })
  }
  if (input.fleetStale) {
    notices.push({
      id: 'fleet',
      tone: 'info',
      text: 'Drone or order data could not be refreshed',
    })
  }
  return notices
}
