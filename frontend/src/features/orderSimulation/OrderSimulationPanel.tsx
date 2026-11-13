import { useState } from 'react'

import { disableOrderSimulation, enableOrderSimulation } from '../../api/orderSimulation'
import { generateOrder } from '../../api/orders'
import { PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { useAction } from '../management/useAction'
import { formatUtcTimestamp } from '../orders/orderStatus'
import { useOrderSimulation } from './useOrderSimulation'

interface OrderSimulationPanelProps {
  /** Called after a manual order was created, so the orders list is re-read at once. */
  onGenerated: () => void
}

/**
 * Operator controls for simulated customer orders (Features 015A/015B). Separate from Automatic
 * Dispatch: it only starts and stops order arrivals and never touches dispatch, drones or flights.
 * It always shows what the server reports; after a click it waits for the backend's answer and
 * then re-reads the status instead of assuming success.
 */
export function OrderSimulationPanel({ onGenerated }: OrderSimulationPanelProps) {
  const { state, stale, retry, refresh } = useOrderSimulation()
  const mode = useAction()
  const generation = useAction()
  const [createdId, setCreatedId] = useState<string | null>(null)

  if (state.status === 'loading') {
    return (
      <section aria-label="Order simulation" className="rounded border border-line p-3">
        <p role="status" className="text-sm text-fg-muted">
          Order simulation: loading…
        </p>
      </section>
    )
  }
  if (state.status === 'error') {
    return (
      <section aria-label="Order simulation" className="rounded border border-line p-3">
        <p className="flex flex-wrap items-center gap-2 text-sm text-fg-muted">
          Order simulation status unavailable
          <button type="button" className={SECONDARY_BUTTON_CLASS} onClick={retry}>
            Retry order simulation
          </button>
        </p>
      </section>
    )
  }

  const {
    enabled,
    workerRunning,
    lastCheckAt,
    lastOutcome,
    outstandingOrders,
    maxOutstandingOrders,
  } = state.data
  const cannotEnable = !enabled && !workerRunning

  const toggle = async () => {
    mode.clearError()
    await mode.run(() => (enabled ? disableOrderSimulation() : enableOrderSimulation()))
    // Either way, show what the server really says now (a refused change leaves it unchanged).
    refresh()
  }
  const generateOne = async () => {
    setCreatedId(null)
    const ok = await generation.run(async () => {
      const order = await generateOrder()
      setCreatedId(order.id)
    })
    if (ok) onGenerated() // the new order shows up without waiting for the next poll
    refresh() // the waiting count changed (or the attempt failed: show the real state)
  }

  return (
    <section
      aria-label="Order simulation"
      className="flex flex-col gap-3 rounded border border-line p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Order simulation</h3>
        <span className="text-xs text-fg-muted">Separate from Automatic Dispatch</span>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-fg-muted">Automatic orders</span>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label="Order simulation"
            className={SECONDARY_BUTTON_CLASS}
            disabled={mode.busy || cannotEnable}
            title={cannotEnable ? 'The simulation worker is not running' : undefined}
            onClick={() => void toggle()}
          >
            {mode.busy ? 'Working…' : enabled ? 'ON' : 'OFF'}
          </button>
        </div>
        <span>
          <span className="text-fg-muted">Worker: </span>
          {workerRunning ? 'Available' : 'Unavailable'}
        </span>
        <span>
          <span className="text-fg-muted">Waiting orders: </span>
          {outstandingOrders} / {maxOutstandingOrders}
        </span>
        <button
          type="button"
          className={PRIMARY_BUTTON_CLASS}
          disabled={generation.busy}
          onClick={() => void generateOne()}
        >
          {generation.busy ? 'Generating…' : 'Generate One Order'}
        </button>
      </div>

      {mode.error && (
        <p role="alert" className="text-xs text-status-critical">
          {mode.error}
        </p>
      )}
      {generation.error && (
        <p role="alert" className="text-xs text-status-critical">
          Could not generate an order: {generation.error}
        </p>
      )}
      {!mode.error && !generation.error && !workerRunning && (
        <p role="status" className="text-xs text-status-warning">
          Simulation worker is not running; automatic generation cannot be enabled.
        </p>
      )}
      {createdId && !generation.error && (
        <p role="status" className="text-xs text-fg-muted">
          Created order {createdId}.
        </p>
      )}

      <p className="text-xs text-fg-muted">
        {lastOutcome
          ? `Last automatic result: ${lastOutcome}${lastCheckAt ? ` (${formatUtcTimestamp(lastCheckAt)})` : ''}`
          : 'No automatic orders yet.'}
      </p>
      <p className="text-xs text-fg-muted">
        Waiting orders counts every order ready for pickup. The limit pauses automatic generation
        only; Generate One Order is not limited by it.
      </p>
      {stale && <p className="text-xs text-fg-muted">Status may be out of date</p>}
    </section>
  )
}
