import { type ReactNode, useState } from 'react'

import { cancelOrder } from '../../api/orders'
import type { Order } from '../../types/order'
import { useAction } from '../management/useAction'
import { CancelConfirmation } from '../orders/CancelOrderAction'
import { ORDER_STATUS_DISPLAY, isCancellable } from '../orders/orderStatus'

interface Scenario {
  id: string
  label: string
  availableIn: string
  icon: ReactNode
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  )
}

const BOX = (
  <>
    <path d="M21 10V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l2-1.1" />
    <path d="M3.3 7 12 12l8.7-5" />
    <path d="M12 22V12" />
  </>
)

const CANCEL_ICON = (
  <Icon>
    {BOX}
    <path d="m17 17 4 4" />
    <path d="m21 17-4 4" />
  </Icon>
)

/** The three future incident scenarios. None is implemented yet, so each control is disabled. */
const SCENARIOS: Scenario[] = [
  {
    id: 'drone-failure',
    label: 'Drone failure',
    availableIn: '018C',
    icon: (
      <Icon>
        <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </Icon>
    ),
  },
  {
    id: 'recipient-unavailable',
    label: 'Recipient unavailable',
    availableIn: '018D',
    icon: (
      <Icon>
        {BOX}
        <path d="M22 16h-6" />
        <path d="m18 13-3 3 3 3" />
      </Icon>
    ),
  },
  {
    id: 'lpr-transit',
    label: 'LPR transit',
    availableIn: '018E',
    icon: (
      <Icon>
        <path d="M4 5h16" />
        <path d="M12 5v3" />
        <path d="M7 12a5 4 0 0 1 5-4h1a4 4 0 0 1 4 4v1a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2z" />
        <path d="M17 11h5" />
        <path d="M6 19h12" />
        <path d="M9 15v4" />
        <path d="M15 15v4" />
      </Icon>
    ),
  },
]

interface SimulationEventsPanelProps {
  /** The order the operator has selected on the map or in the list, if any. */
  selectedOrder?: Order | null
  /** Called after a successful cancellation so the operational views are re-read at once. */
  onOrderCancelled?: () => void
}

/**
 * Simulation Events controls: an MVP/demo-only cluster. "Cancel order" (Feature 018B) acts on the
 * selected order after an explicit confirmation and shows what the backend answers; the other
 * three scenarios stay visible but disabled until Features 018C to 018E implement real backend
 * behavior. The Random incidents switch is disabled for the same reason and does not claim that
 * incidents are being produced.
 */
export function SimulationEventsPanel({
  selectedOrder = null,
  onOrderCancelled,
}: SimulationEventsPanelProps) {
  const cancellation = useAction()
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [cancelled, setCancelled] = useState<string | null>(null)

  const eligible = selectedOrder !== null && isCancellable(selectedOrder)
  const confirming = eligible && confirmingId === selectedOrder.id

  let hint = 'Select an order (map, Orders list or table)'
  if (selectedOrder && eligible) hint = `Cancel ${selectedOrder.id}`
  if (selectedOrder && !eligible) {
    hint = `Not available: ${ORDER_STATUS_DISPLAY[selectedOrder.status].label.toLowerCase()}`
  }

  const confirm = async () => {
    if (!selectedOrder) return
    const id = selectedOrder.id
    const ok = await cancellation.run(() => cancelOrder(id))
    if (ok) {
      setConfirmingId(null)
      setCancelled(id)
    }
    // Whatever the answer was, the state may have changed (for example the parcel was just
    // delivered): show the backend's truth now instead of waiting for the next poll.
    onOrderCancelled?.()
  }

  return (
    <section aria-label="Simulation events" className="rounded border border-line p-3">
      <h3 className="text-sm font-semibold">
        Simulation events <span className="font-normal text-fg-muted">(demo only)</span>
      </h3>
      <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <li>
          <button
            type="button"
            disabled={!eligible || cancellation.busy}
            title={hint}
            onClick={() => {
              cancellation.clearError()
              setCancelled(null)
              if (selectedOrder) setConfirmingId(selectedOrder.id)
            }}
            className="flex w-full flex-col items-center gap-1 rounded border border-line px-2 py-2 text-xs text-fg hover:bg-surface-raised disabled:cursor-not-allowed disabled:text-fg-muted disabled:opacity-60 disabled:hover:bg-transparent"
          >
            {CANCEL_ICON}
            <span>Cancel order</span>
            <span className="text-[11px] text-fg-muted">{hint}</span>
          </button>
        </li>
        {SCENARIOS.map((scenario) => (
          <li key={scenario.id}>
            <button
              type="button"
              disabled
              title={`${scenario.label}: coming in ${scenario.availableIn}`}
              className="flex w-full flex-col items-center gap-1 rounded border border-line px-2 py-2 text-xs text-fg-muted opacity-60 disabled:cursor-not-allowed"
            >
              {scenario.icon}
              <span>{scenario.label}</span>
              <span className="text-[11px]">Coming in {scenario.availableIn}</span>
            </button>
          </li>
        ))}
      </ul>
      {confirming && (
        <CancelConfirmation
          order={selectedOrder}
          busy={cancellation.busy}
          onConfirm={confirm}
          onKeep={() => setConfirmingId(null)}
        />
      )}
      {cancellation.error && (
        <p role="alert" className="mt-2 text-xs text-status-critical">
          {cancellation.error}
        </p>
      )}
      {cancelled && selectedOrder?.id === cancelled && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          Order {cancelled} cancelled.
        </p>
      )}
      <div className="mt-3 flex items-start gap-2 text-xs text-fg-muted">
        <button
          type="button"
          role="switch"
          aria-checked="false"
          aria-describedby="random-incidents-note"
          disabled
          className="mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-line px-0.5 opacity-60 disabled:cursor-not-allowed"
        >
          <span className="sr-only">Random incidents</span>
          <span aria-hidden="true" className="size-3.5 rounded-full bg-fg-muted" />
        </button>
        <div>
          <p className="text-sm text-fg">Random incidents</p>
          <p id="random-incidents-note">Available when incident scenarios are enabled.</p>
        </div>
      </div>
    </section>
  )
}
