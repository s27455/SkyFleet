import { useState } from 'react'

import { cancelOrder } from '../../api/orders'
import type { Order } from '../../types/order'
import { DANGER_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { useAction } from '../management/useAction'
import { isCancellable } from './orderStatus'

interface CancelConfirmationProps {
  order: Pick<Order, 'id' | 'status'>
  busy: boolean
  onConfirm: () => void
  onKeep: () => void
}

/** The explicit confirmation shared by every place that can cancel an order. */
export function CancelConfirmation({ order, busy, onConfirm, onKeep }: CancelConfirmationProps) {
  return (
    <div
      role="group"
      aria-label="Confirm cancellation"
      className="mt-3 rounded border border-status-critical p-3 text-sm"
    >
      <p>
        Cancel order <span className="font-mono">{order.id}</span>? Cancellation is permanent for
        this order.
        {order.status === 'OUT_FOR_DELIVERY' &&
          ' A drone is on its way with the parcel: it will return to the nearest reachable Hub.'}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={DANGER_BUTTON_CLASS} disabled={busy} onClick={onConfirm}>
          {busy ? 'Cancelling…' : 'Confirm cancellation'}
        </button>
        <button type="button" className={SECONDARY_BUTTON_CLASS} disabled={busy} onClick={onKeep}>
          Keep order
        </button>
      </div>
    </div>
  )
}

interface CancelOrderActionProps {
  order: Order
  /** Called after every answer (also a refusal: the state may have changed meanwhile). */
  onCancelled: () => void
}

/**
 * The visible "Cancel order" action of the order details: a button, an explicit confirmation, a
 * pending state, and the backend's refusal as readable text. Success is announced only after the
 * backend confirmed the cancellation; an error is never shown as a success.
 */
export function CancelOrderAction({ order, onCancelled }: CancelOrderActionProps) {
  const action = useAction()
  const [confirming, setConfirming] = useState(false)

  if (!isCancellable(order)) return null

  const confirm = async () => {
    const ok = await action.run(() => cancelOrder(order.id))
    if (ok) setConfirming(false)
    // Whatever the answer was, show the backend's truth now instead of waiting for the next poll.
    onCancelled()
  }

  return (
    <section aria-label="Cancel order" className="mt-3">
      {!confirming && (
        <button
          type="button"
          className={`${DANGER_BUTTON_CLASS} w-full`}
          onClick={() => {
            action.clearError()
            setConfirming(true)
          }}
        >
          Cancel order
        </button>
      )}
      {confirming && (
        <CancelConfirmation
          order={order}
          busy={action.busy}
          onConfirm={confirm}
          onKeep={() => setConfirming(false)}
        />
      )}
      {action.error && (
        <p role="alert" className="mt-2 text-xs text-status-critical">
          {action.error}
        </p>
      )}
    </section>
  )
}
