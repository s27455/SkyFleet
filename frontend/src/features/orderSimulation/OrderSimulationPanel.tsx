import { useState } from 'react'

import { generateOrder } from '../../api/orders'
import { PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { useAction } from '../management/useAction'
import { formatUtcTimestamp } from '../orders/orderStatus'
import type { OrderSimulationStatus } from '../../types/orderSimulation'
import type { PolledResource } from '../data/usePolledResource'

interface OrderSimulationPanelProps {
  /** Called after a manual order was created, so the orders list is re-read at once. */
  onGenerated: () => void
  /** The shared poll of the order simulation state (the header switch reads the same one). */
  resource: PolledResource<OrderSimulationStatus>
}

/**
 * Order statistics and manual generation (Features 015A/015B); the Automatic orders switch is in the header. Separate from Automatic
 * Dispatch: it only starts and stops order arrivals and never touches dispatch, drones or flights.
 * It always shows what the server reports; after a click it waits for the backend's answer and
 * then re-reads the status instead of assuming success.
 */
export function OrderSimulationPanel({ onGenerated, resource }: OrderSimulationPanelProps) {
  const { state, stale, retry, refresh } = resource
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

  const { workerRunning, lastCheckAt, lastOutcome, outstandingOrders, maxOutstandingOrders } =
    state.data
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
        <span className="text-xs text-fg-muted">Switch: Automatic orders in the header</span>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
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

      {generation.error && (
        <p role="alert" className="text-xs text-status-critical">
          Could not generate an order: {generation.error}
        </p>
      )}
      {!generation.error && !workerRunning && (
        <p role="status" className="text-xs text-status-warning">
          Simulation worker is not running; automatic orders cannot be enabled.
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
