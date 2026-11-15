import {
  COPILOT_ERROR_CODES,
  type CopilotAnswer,
  type CopilotErrorCode,
  type CopilotFailure,
  type NamedDroneNote,
  type SnapshotInfo,
} from '../types/copilot'
import { ApiError, apiGet, apiSend } from './client'

const BASE = '/api/ai/copilot'

function invalid(reason: string): never {
  throw new ApiError(`Invalid Copilot data: ${reason}`)
}

const isCount = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

/** Whether the server can answer questions at all. Generic: no reason, no setting. */
export async function getCopilotStatus(signal?: AbortSignal): Promise<boolean> {
  const payload = await apiGet<unknown>(`${BASE}/status`, signal)
  if (typeof payload !== 'object' || payload === null) invalid('status is not an object')
  const { available } = payload as { available?: unknown }
  if (typeof available !== 'boolean') invalid('status.available is not a boolean')
  return available
}

function toSnapshot(payload: unknown): SnapshotInfo {
  if (typeof payload !== 'object' || payload === null) invalid('snapshot is not an object')
  const raw = payload as Record<string, unknown>
  if (typeof raw.captured_at !== 'string' || raw.captured_at === '') invalid('captured_at')
  if (raw.data_status !== 'complete' && raw.data_status !== 'degraded') invalid('data_status')
  if (typeof raw.truncated !== 'boolean') invalid('truncated')
  if (
    !Array.isArray(raw.limitations) ||
    !raw.limitations.every((item) => typeof item === 'string')
  ) {
    invalid('limitations')
  }
  const omitted = raw.omitted as Record<string, unknown> | null
  if (
    typeof omitted !== 'object' ||
    omitted === null ||
    !isCount(omitted.drones) ||
    !isCount(omitted.hubs) ||
    !isCount(omitted.active_incidents) ||
    !isCount(omitted.recovered_alerts)
  ) {
    invalid('omitted')
  }
  if (!Array.isArray(raw.named_drones)) invalid('named_drones')
  const namedDrones: NamedDroneNote[] = raw.named_drones.map((item: unknown) => {
    const note = item as Record<string, unknown> | null
    if (
      typeof note !== 'object' ||
      note === null ||
      typeof note.id !== 'string' ||
      typeof note.exists !== 'boolean' ||
      typeof note.listed !== 'boolean'
    ) {
      invalid('named drone')
    }
    return { id: note.id, exists: note.exists, listed: note.listed }
  })
  return {
    capturedAt: raw.captured_at,
    dataStatus: raw.data_status,
    truncated: raw.truncated,
    limitations: raw.limitations as string[],
    omitted: {
      drones: omitted.drones,
      hubs: omitted.hubs,
      activeIncidents: omitted.active_incidents,
      recoveredAlerts: omitted.recovered_alerts,
    },
    namedDrones,
  }
}

function toAnswer(payload: unknown): CopilotAnswer {
  if (typeof payload !== 'object' || payload === null) invalid('answer is not an object')
  const raw = payload as Record<string, unknown>
  if (typeof raw.answer !== 'string') invalid('answer')
  if (typeof raw.answer_cut_off !== 'boolean') invalid('answer_cut_off')
  return {
    answer: raw.answer,
    answerCut: raw.answer_cut_off,
    snapshot: toSnapshot(raw.snapshot),
  }
}

/**
 * Asks ONE question. The operator token goes in the Authorization header only (never in the URL
 * or the body) and is not kept anywhere by this module. There is no retry here and none anywhere
 * above it: a failed or unclear request is shown to the operator, who decides.
 */
export async function askCopilot(question: string, token: string): Promise<CopilotAnswer> {
  const payload = await apiSend<unknown>('POST', `${BASE}/ask`, { question }, undefined, {
    Authorization: `Bearer ${token}`,
  })
  return toAnswer(payload)
}

const UNKNOWN_OUTCOME = 'The outcome of the request is unknown.'

/** Shown with every failure that may have reached the provider. Nothing retries such a request. */
export const CHARGE_WARNING =
  'This request may have been charged. It will not be retried automatically: check the AI ledger ' +
  'and the provider Console before asking again.'

/** Fixed texts, so what the operator reads never depends on text sent by the server. */
const MESSAGES: Record<CopilotErrorCode, string> = {
  ORIGIN_NOT_ALLOWED: 'This page is not allowed to use the AI Copilot (the origin check failed).',
  AI_DISABLED: 'The AI Copilot is disabled on this server.',
  AI_MISCONFIGURED: 'The AI Copilot is not correctly configured on this server.',
  UNAUTHORIZED: 'The access token was not accepted. Check it and enter it again.',
  AUTH_THROTTLED: 'Too many failed attempts. Wait before trying again.',
  INVALID_QUESTION:
    "The question was not accepted. Use 1 to 500 characters and avoid the words 'fleet context'.",
  CONTEXT_TOO_LARGE: 'The question and the fleet snapshot do not fit the AI request size limit.',
  RATE_LIMITED: 'AI requests are limited. Wait before asking again.',
  BUDGET_EXHAUSTED: 'The AI budget is exhausted. No more questions can be asked.',
  AI_HALTED: 'The AI Copilot stopped itself and must be reviewed by an operator.',
  PROVIDER_UNAVAILABLE: 'The AI provider is unavailable. Try again later.',
  ACCOUNTING_UNAVAILABLE: 'The AI budget could not be read, so no request was sent.',
  CONTEXT_UNAVAILABLE: 'The fleet snapshot could not be built, so no AI request was made.',
  INTERNAL_ERROR: 'The AI Copilot failed unexpectedly.',
}

function isCode(value: unknown): value is CopilotErrorCode {
  return typeof value === 'string' && (COPILOT_ERROR_CODES as readonly string[]).includes(value)
}

/**
 * Turns whatever went wrong into one failure the operator can act on.
 *
 * When the request may have been charged (the provider's outcome was unclear, the connection was
 * lost while waiting, or the server's answer could not be read) the failure says so, and nothing
 * ever retries it.
 */
export function toCopilotFailure(error: unknown): CopilotFailure {
  if (!(error instanceof ApiError)) {
    return {
      code: 'UNKNOWN',
      message: UNKNOWN_OUTCOME,
      retryAfterSeconds: null,
      chargePossible: true,
    }
  }
  const { status, detail } = error
  const body =
    typeof detail === 'object' && detail !== null ? (detail as Record<string, unknown>) : {}
  if (status === undefined || (status >= 200 && status < 300)) {
    // no response at all, or a success whose body could not be read: the server may have answered
    return {
      code: 'CONNECTION_LOST',
      message: UNKNOWN_OUTCOME,
      retryAfterSeconds: null,
      chargePossible: true,
    }
  }
  const retry = typeof body.retry_after_seconds === 'number' ? body.retry_after_seconds : null
  if (!isCode(body.code)) {
    // an error that is not the Copilot's (a proxy page, a crash): unclear above all for 5xx
    const unclear = status >= 500
    return {
      code: 'UNKNOWN',
      message: unclear ? UNKNOWN_OUTCOME : `The server rejected the request (status ${status}).`,
      retryAfterSeconds: null,
      chargePossible: unclear,
    }
  }
  const chargePossible = body.charge_possible === true
  let message = MESSAGES[body.code]
  if (body.code === 'PROVIDER_UNAVAILABLE' && body.charge_possible === true) {
    message = UNKNOWN_OUTCOME
  } else if (body.code === 'PROVIDER_UNAVAILABLE' && body.charge_possible === false) {
    message = 'The AI provider rejected the request. No charge is expected.'
  }
  return { code: body.code, message, retryAfterSeconds: retry, chargePossible }
}
