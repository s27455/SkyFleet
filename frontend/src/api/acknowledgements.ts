import { ApiError, apiPost } from './client'

/** Mirrors `EmergencyAcknowledgement` (`POST /api/incidents/emergencies/{mission_id}/acknowledge`). */
export interface EmergencyAcknowledgement {
  missionId: string
  acknowledgedAt: string
}

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && HAS_ZONE.test(value) && !Number.isNaN(Date.parse(value))

/**
 * Acknowledges one emergency alert (Feature 022). The backend stores it once and answers with the
 * original time on repeats, so the call is safe to repeat. It only hides the alert in the map
 * overlay: the incident, its events and the drone are not changed. Rejects with `ApiError` (for
 * example 404 `EMERGENCY_NOT_FOUND`, or a server error while the database is not migrated yet), and
 * an answer for a different mission counts as an error.
 */
export async function acknowledgeEmergency(missionId: string): Promise<EmergencyAcknowledgement> {
  const raw = await apiPost<unknown>(
    `/api/incidents/emergencies/${encodeURIComponent(missionId)}/acknowledge`,
  )
  if (typeof raw !== 'object' || raw === null) {
    throw new ApiError('Invalid acknowledgement data: not an object')
  }
  const { mission_id: id, acknowledged_at: at } = raw as Record<string, unknown>
  if (id !== missionId) throw new ApiError('Invalid acknowledgement data: wrong mission')
  if (!isTimestamp(at)) throw new ApiError('Invalid acknowledgement data: bad time')
  return { missionId: id, acknowledgedAt: at }
}
