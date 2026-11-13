/** Mirrors `AutoDispatchStatus` in backend/app/dispatch/schemas.py (`GET /api/dispatch/auto/status`). */
export interface AutoDispatchStatusResponse {
  enabled: boolean
  worker_running: boolean
  last_check_at: string | null
  last_outcome: string | null
}

/** What the server is actually doing; the UI never assumes it. */
export interface AutoDispatchStatus {
  /** True only while the mode is ON and the simulation worker (the loop's owner) is alive. */
  enabled: boolean
  workerRunning: boolean
  /** ISO 8601 time of the last automatic pass, or null if there has been none. */
  lastCheckAt: string | null
  /** A short summary of the last pass, written by the backend. */
  lastOutcome: string | null
}
