import { disableOrderSimulation, enableOrderSimulation } from '../../api/orderSimulation'
import type { OrderSimulationStatus } from '../../types/orderSimulation'
import type { PolledResource } from '../data/usePolledResource'
import { useAction } from '../management/useAction'

const BUTTON_CLASS =
  'rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-raised disabled:cursor-not-allowed disabled:opacity-50'

interface OrderGenerationControlProps {
  /** The one shared poll of the backend's order simulation state (owned by the caller). */
  resource: PolledResource<OrderSimulationStatus>
}

/**
 * Compact Automatic orders switch for the header (it only starts and stops order arrivals; it is
 * separate from Auto Dispatch). Like the other switches it shows what the server reports and never
 * flips on its own: after a click it waits for the backend's answer, then re-reads the status.
 */
export function OrderGenerationControl({ resource }: OrderGenerationControlProps) {
  const { state, retry, refresh } = resource
  const { busy, error, run, clearError } = useAction()

  if (state.status === 'loading') {
    return <span className="text-sm text-fg-muted">Automatic orders: loading…</span>
  }
  if (state.status === 'error') {
    return (
      <span className="flex items-center gap-2 text-sm text-fg-muted">
        Automatic orders unavailable
        <button type="button" className={BUTTON_CLASS} onClick={retry}>
          Retry automatic orders
        </button>
      </span>
    )
  }

  const { enabled, workerRunning } = state.data
  const cannotEnable = !enabled && !workerRunning
  const toggle = async () => {
    clearError()
    await run(() => (enabled ? disableOrderSimulation() : enableOrderSimulation()))
    // Either way, show what the server really says now (a refused change leaves it unchanged).
    refresh()
  }

  return (
    <div className="flex flex-col items-end gap-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm text-fg-muted">Automatic orders</span>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Automatic orders"
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
    </div>
  )
}
