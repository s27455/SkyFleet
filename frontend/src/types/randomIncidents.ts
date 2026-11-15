/** Mirrors `RandomIncidentsStatus` in backend/app/simulation/schemas.py (`GET /api/incidents/random`). */
export interface RandomIncidentsStatusResponse {
  enabled: boolean
  worker_running: boolean
  last_check_at: string | null
  last_outcome: string | null
}

/** What the server is actually doing; the UI never assumes it. */
export interface RandomIncidentsStatus {
  /** True only while the mode is ON and the simulation worker (the scheduler's owner) is alive. */
  enabled: boolean
  workerRunning: boolean
  /** ISO 8601 time of the last scheduled attempt, or null if there has been none. */
  lastCheckAt: string | null
  /** A short summary of the last attempt (triggered, skipped or an error), written by the backend. */
  lastOutcome: string | null
}
