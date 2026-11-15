/** The AI Copilot (Feature 026): a read-only assistant, one question and one answer at a time. */

export type SnapshotStatus = 'complete' | 'degraded'

/** What the server could say about a drone the question named. */
export interface NamedDroneNote {
  id: string
  /** false: no such drone is in the fleet. */
  exists: boolean
  /** false: the drone exists but its row was not in the snapshot the model saw. */
  listed: boolean
}

/** Facts about the snapshot the answer is based on, taken from the server (never from the model). */
export interface SnapshotInfo {
  /** ISO 8601 UTC. */
  capturedAt: string
  dataStatus: SnapshotStatus
  truncated: boolean
  /** Fixed server codes such as `WORKER_NOT_RUNNING` or `DRONES_OMITTED:7`. */
  limitations: string[]
  omitted: { drones: number; hubs: number; activeIncidents: number; recoveredAlerts: number }
  namedDrones: NamedDroneNote[]
}

export interface CopilotAnswer {
  /** Untrusted text: it is only ever shown as plain text. */
  answer: string
  /** The model stopped at its output limit. */
  answerCut: boolean
  snapshot: SnapshotInfo
}

export const COPILOT_ERROR_CODES = [
  'ORIGIN_NOT_ALLOWED',
  'AI_DISABLED',
  'AI_MISCONFIGURED',
  'UNAUTHORIZED',
  'AUTH_THROTTLED',
  'INVALID_QUESTION',
  'CONTEXT_TOO_LARGE',
  'RATE_LIMITED',
  'BUDGET_EXHAUSTED',
  'AI_HALTED',
  'PROVIDER_UNAVAILABLE',
  'ACCOUNTING_UNAVAILABLE',
  'CONTEXT_UNAVAILABLE',
  'INTERNAL_ERROR',
] as const
export type CopilotErrorCode = (typeof COPILOT_ERROR_CODES)[number]

/** Why a question failed, in words the operator can act on. */
export interface CopilotFailure {
  /** A server code, or `CONNECTION_LOST` / `UNKNOWN` when the server's answer is not usable. */
  code: CopilotErrorCode | 'CONNECTION_LOST' | 'UNKNOWN'
  message: string
  retryAfterSeconds: number | null
  /**
   * The request may have reached the provider and been charged. It is NEVER retried automatically;
   * the operator must look at the AI ledger and the provider Console first.
   */
  chargePossible: boolean
}
