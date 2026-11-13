import { disableAutoDispatch, enableAutoDispatch } from '../../api/dispatch'
import { formatUtcTimestamp } from '../orders/orderStatus'
import { useAction } from '../management/useAction'
import { useAutoDispatch } from './useAutoDispatch'

const BUTTON_CLASS =
  'rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-raised disabled:cursor-not-allowed disabled:opacity-50'

/**
 * Compact Auto Dispatch switch for the header. It always shows what the server reports and never
 * flips on its own: after a click it waits for the backend's answer, then re-reads the status.
 */
export function AutoDispatchControl() {
  const { state, stale, retry, refresh } = useAutoDispatch()
  const { busy, error, run, clearError } = useAction()

  if (state.status === 'loading') {
    return (
      <span role="status" className="text-sm text-fg-muted">
        Auto dispatch: loading…
      </span>
    )
  }
  if (state.status === 'error') {
    return (
      <span className="flex items-center gap-2 text-sm text-fg-muted">
        Auto dispatch status unavailable
        <button type="button" className={BUTTON_CLASS} onClick={retry}>
          Retry auto dispatch
        </button>
      </span>
    )
  }

  const { enabled, workerRunning, lastCheckAt, lastOutcome } = state.data
  const toggle = async () => {
    clearError()
    const ok = await run(() => (enabled ? disableAutoDispatch() : enableAutoDispatch()))
    // Either way, show what the server really says now (a refused change leaves it unchanged).
    refresh()
    return ok
  }
  const cannotEnable = !enabled && !workerRunning

  return (
    <div className="flex flex-col items-end gap-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm text-fg-muted">Auto dispatch</span>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Auto dispatch"
          className={BUTTON_CLASS}
          disabled={busy || cannotEnable}
          title={cannotEnable ? 'The simulation worker is not running' : undefined}
          onClick={() => void toggle()}
        >
          {busy ? 'Working…' : enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      {error && (
        <p role="alert" className="max-w-72 text-right text-xs text-status-critical">
          {error}
        </p>
      )}
      {!error && !workerRunning && (
        <p role="status" className="max-w-72 text-right text-xs text-status-warning">
          Simulation worker is not running
        </p>
      )}
      {!error && workerRunning && lastOutcome && (
        <p className="hidden max-w-72 text-right text-xs text-fg-muted sm:block">
          {lastOutcome}
          {lastCheckAt ? ` (${formatUtcTimestamp(lastCheckAt)})` : ''}
        </p>
      )}
      {stale && <p className="text-xs text-fg-muted">Status may be out of date</p>}
    </div>
  )
}
