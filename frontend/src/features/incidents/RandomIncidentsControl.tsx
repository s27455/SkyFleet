import {
  disableRandomIncidents,
  enableRandomIncidents,
  isWorkerUnavailable,
} from '../../api/randomIncidents'
import { ApiError } from '../../api/client'
import type { RandomIncidentsStatus } from '../../types/randomIncidents'
import type { PolledResource } from '../data/usePolledResource'
import { SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { useAction } from '../management/useAction'
import { formatUtcTimestamp } from '../orders/orderStatus'

const WORKER_DOWN_MESSAGE =
  'The simulation worker is not running, so Random incidents cannot be enabled. Start it and try again.'

interface RandomIncidentsControlProps {
  /** The one shared poll of the backend's Random Incidents state (owned by `App`). */
  resource: PolledResource<RandomIncidentsStatus>
}

/**
 * The Random incidents switch of the Scenarios menu (Feature 021D-2). It shows only what the server
 * reports and never flips on its own: after a click it waits for the backend's answer, then
 * re-reads the status. While ON the worker makes an *attempt* every few minutes; an attempt may be
 * skipped, so no incident is promised.
 */
export function RandomIncidentsControl({ resource }: RandomIncidentsControlProps) {
  const { state, stale, retry, refresh } = resource
  const { busy, error, run, clearError } = useAction()

  if (state.status === 'loading') {
    return (
      <p role="status" className="mt-3 text-xs text-fg-muted">
        Random incidents: loading…
      </p>
    )
  }
  if (state.status === 'error') {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
        Random incidents status unavailable
        <button type="button" className={SECONDARY_BUTTON_CLASS} onClick={retry}>
          Retry random incidents
        </button>
      </div>
    )
  }

  const { enabled, workerRunning, lastCheckAt, lastOutcome } = state.data
  const cannotEnable = !enabled && !workerRunning

  const toggle = async () => {
    clearError()
    await run(async () => {
      try {
        await (enabled ? disableRandomIncidents() : enableRandomIncidents())
      } catch (caught) {
        if (isWorkerUnavailable(caught)) {
          throw new ApiError(WORKER_DOWN_MESSAGE, 503, { message: WORKER_DOWN_MESSAGE })
        }
        throw caught
      }
    })
    // Either way, show what the server really says now (a refused change leaves it unchanged).
    refresh()
  }

  return (
    <div className="mt-3 flex items-start gap-2 text-xs text-fg-muted">
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label="Random incidents"
        aria-describedby="random-incidents-note"
        disabled={busy || cannotEnable}
        title={cannotEnable ? 'The simulation worker is not running' : undefined}
        onClick={() => void toggle()}
        className={`mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full border px-0.5 focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60 ${
          enabled ? 'justify-end border-accent bg-accent/30' : 'justify-start border-line'
        }`}
      >
        <span
          aria-hidden="true"
          className={`size-3.5 rounded-full ${enabled ? 'bg-accent' : 'bg-fg-muted'}`}
        />
      </button>
      <div className="min-w-0">
        <p className="text-sm text-fg">
          Random incidents{' '}
          <span className="font-mono text-xs text-fg-muted">
            {busy ? 'Working…' : enabled ? 'ON' : 'OFF'}
          </span>
        </p>
        <p id="random-incidents-note">
          {enabled
            ? 'The worker tries one incident every few minutes; an attempt may be skipped.'
            : 'Off: no incidents are triggered automatically.'}
        </p>
        {error && (
          <p role="alert" className="mt-1 text-status-critical">
            {error}
          </p>
        )}
        {!error && !workerRunning && (
          <p role="status" className="mt-1 text-status-warning">
            Simulation worker is not running
          </p>
        )}
        {workerRunning && lastOutcome && (
          <p className="mt-1">
            Last attempt: {lastOutcome}
            {lastCheckAt ? ` (${formatUtcTimestamp(lastCheckAt)})` : ''}
          </p>
        )}
        {enabled && workerRunning && !lastOutcome && <p className="mt-1">No attempt yet.</p>}
        {stale && <p className="mt-1">Status may be out of date</p>}
      </div>
    </div>
  )
}
