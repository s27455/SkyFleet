import { type ReactNode, useEffect, useState } from 'react'

import {
  activateRainWarning,
  clearRainWarning,
  isLprAlreadyActive,
  isNoEligibleTarget,
  triggerDroneFailure,
  triggerLprHelicopter,
  triggerRecipientUnavailable,
} from '../../api/incidents'
import { cancelOrder } from '../../api/orders'
import type { Order } from '../../types/order'
import { useAction } from '../management/useAction'
import { CancelConfirmation } from '../orders/CancelOrderAction'
import { ORDER_STATUS_DISPLAY, isCancellable } from '../orders/orderStatus'

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

const DRONE_FAILURE_ICON = (
  <Icon>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </Icon>
)

const RECIPIENT_ICON = (
  <Icon>
    {BOX}
    <path d="M22 16h-6" />
    <path d="m18 13-3 3 3 3" />
  </Icon>
)

const RAIN_ICON = (
  <Icon>
    <path d="M4 14a4 4 0 0 1 1-7.9 6 6 0 0 1 11.6 1.4A3.5 3.5 0 0 1 17 14z" />
    <path d="M8 18l-1 3" />
    <path d="M12 18l-1 3" />
    <path d="M16 18l-1 3" />
  </Icon>
)

const LPR_ICON = (
  <Icon>
    <path d="M4 5h16" />
    <path d="M12 5v3" />
    <path d="M7 12a5 4 0 0 1 5-4h1a4 4 0 0 1 4 4v1a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2z" />
    <path d="M17 11h5" />
    <path d="M6 19h12" />
    <path d="M9 15v4" />
    <path d="M15 15v4" />
  </Icon>
)

export interface SimulationEventsPanelProps {
  /** The order the operator has selected on the map or in the list, if any. */
  selectedOrder?: Order | null
  /** Called after a successful cancellation so the operational views are re-read at once. */
  onOrderCancelled?: () => void
  /** Whether the flights show a drone a failure could interrupt (the backend decides). */
  canFailDrone?: boolean
  /** Called after a Drone failure request (whatever the answer) so the views are re-read. */
  onDroneFailed?: () => void
  /** Whether a delivery is on its way that could still fail at the handover (backend decides). */
  canMarkRecipient?: boolean
  /** Called after a Recipient unavailable request (whatever the answer) so the views refresh. */
  onRecipientMarked?: () => void
  /** Whether the LPR helicopter is crossing the area now (the backend allows only one at a time). */
  lprActive?: boolean
  /** Called after an LPR helicopter request (whatever the answer) so the views refresh. */
  onLprTriggered?: () => void
  /** Whether the global rain warning is active (the backend is the source of truth). */
  rainWarningActive?: boolean
  /** Called after an activate or clear request (whatever the answer) so the views refresh. */
  onRainWarningChanged?: () => void
  /**
   * Reports whether an action is waiting for the operator's answer (a cancel confirmation) or for
   * the backend, so a menu around this panel does not close and lose it by accident.
   */
  onPendingChange?: (pending: boolean) => void
}

/**
 * Simulation Events controls: an MVP/demo-only cluster. "Cancel order" (Feature 018B) acts on the
 * selected order after an explicit confirmation and shows what the backend answers. "Drone failure"
 * (Feature 018C) asks the backend to fail one eligible flying drone; the backend chooses it.
 * "Recipient unavailable" (Feature 018D) marks one delivery on its way; the failure is pending until
 * the drone reaches the destination. "LPR helicopter" (Feature 018E) starts one helicopter pass
 * with a moving safety zone; only one runs at a time. The Random incidents switch is disabled for the same reason and does not claim that
 * incidents are being produced.
 */
export function SimulationEventsPanel({
  selectedOrder = null,
  onOrderCancelled,
  canFailDrone = false,
  onDroneFailed,
  canMarkRecipient = false,
  onRecipientMarked,
  lprActive = false,
  onLprTriggered,
  rainWarningActive = false,
  onRainWarningChanged,
  onPendingChange,
}: SimulationEventsPanelProps) {
  const cancellation = useAction()
  const rainAction = useAction()
  const lprAction = useAction()
  const [lprNote, setLprNote] = useState<string | null>(null)
  const failure = useAction()
  const recipient = useAction()
  const [recipientNote, setRecipientNote] = useState<{
    kind: 'done' | 'none'
    text: string
  } | null>(null)
  const [failureNote, setFailureNote] = useState<{ kind: 'done' | 'none'; text: string } | null>(
    null,
  )
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [cancelled, setCancelled] = useState<string | null>(null)

  const eligible = selectedOrder !== null && isCancellable(selectedOrder)
  const confirming = eligible && confirmingId === selectedOrder.id

  const pending =
    confirming ||
    cancellation.busy ||
    failure.busy ||
    recipient.busy ||
    lprAction.busy ||
    rainAction.busy
  useEffect(() => {
    onPendingChange?.(pending)
  }, [pending, onPendingChange])

  let hint = 'Select an order (map, Orders list or table)'
  if (selectedOrder && eligible) hint = `Cancel ${selectedOrder.id}`
  if (selectedOrder && !eligible) {
    hint = `Not available: ${ORDER_STATUS_DISPLAY[selectedOrder.status].label.toLowerCase()}`
  }

  const failDrone = async () => {
    setFailureNote(null)
    await failure.run(async () => {
      try {
        const result = await triggerDroneFailure()
        setFailureNote({
          kind: 'done',
          text: `Drone ${result.droneId} failed: emergency landing in progress.`,
        })
      } catch (error) {
        // Nothing eligible is a clear answer, not a fault: no incident was created.
        if (!isNoEligibleTarget(error)) throw error
        setFailureNote({
          kind: 'none',
          text: 'No drone is flying a mission that a failure could interrupt.',
        })
      }
    })
    onDroneFailed?.() // the state may have changed whatever the answer was
  }

  const toggleRainWarning = async () => {
    await rainAction.run(rainWarningActive ? clearRainWarning : activateRainWarning)
    onRainWarningChanged?.() // the state may have changed whatever the answer was
  }

  const startLpr = async () => {
    setLprNote(null)
    await lprAction.run(async () => {
      try {
        await triggerLprHelicopter()
        setLprNote(
          'LPR helicopter started. A safety zone moves with it; drones in its way wait until it has passed.',
        )
      } catch (error) {
        // A second helicopter is refused clearly: nothing was started, and that is not a fault.
        if (!isLprAlreadyActive(error)) throw error
        setLprNote('An LPR helicopter is already crossing the area.')
      }
    })
    onLprTriggered?.() // the state may have changed whatever the answer was
  }

  const markRecipient = async () => {
    setRecipientNote(null)
    await recipient.run(async () => {
      try {
        const result = await triggerRecipientUnavailable()
        // The order is not failed yet: say what happens, not that it already did.
        setRecipientNote({
          kind: 'done',
          text: `Recipient unavailable reported for ${result.orderId} (drone ${result.droneId}). The delivery fails when the drone reaches the destination.`,
        })
      } catch (error) {
        if (!isNoEligibleTarget(error)) throw error
        setRecipientNote({
          kind: 'none',
          text: 'No drone is on its way to a delivery that could still fail at the handover.',
        })
      }
    })
    onRecipientMarked?.() // the state may have changed whatever the answer was
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
    <section aria-label="Simulation events" className="p-3">
      <h3 className="text-sm font-semibold">
        Simulation events <span className="font-normal text-fg-muted">(demo only)</span>
      </h3>
      <ul className="mt-2 flex flex-col gap-1.5">
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
            className="grid min-h-10 w-full grid-cols-[auto_1fr] items-center gap-x-3 rounded border border-line px-2 py-1.5 text-left text-xs text-fg hover:bg-surface-raised disabled:cursor-not-allowed disabled:text-fg-muted disabled:opacity-60 disabled:hover:bg-transparent [&>svg]:row-span-2"
          >
            {CANCEL_ICON}
            <span>Cancel order</span>
            <span className="text-[11px] text-fg-muted">{hint}</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            disabled={!canFailDrone || failure.busy}
            title={canFailDrone ? 'Fail one flying drone' : 'No drone is flying'}
            onClick={failDrone}
            className="grid min-h-10 w-full grid-cols-[auto_1fr] items-center gap-x-3 rounded border border-line px-2 py-1.5 text-left text-xs text-fg hover:bg-surface-raised disabled:cursor-not-allowed disabled:text-fg-muted disabled:opacity-60 disabled:hover:bg-transparent [&>svg]:row-span-2"
          >
            {DRONE_FAILURE_ICON}
            <span>Drone failure</span>
            <span className="text-[11px] text-fg-muted">
              {failure.busy
                ? 'Triggering…'
                : canFailDrone
                  ? 'Fail a flying drone'
                  : 'No drone is flying'}
            </span>
          </button>
        </li>
        <li>
          <button
            type="button"
            disabled={!canMarkRecipient || recipient.busy}
            title={
              canMarkRecipient
                ? 'Mark one delivery on its way as recipient unavailable'
                : 'No delivery is on its way'
            }
            onClick={markRecipient}
            className="grid min-h-10 w-full grid-cols-[auto_1fr] items-center gap-x-3 rounded border border-line px-2 py-1.5 text-left text-xs text-fg hover:bg-surface-raised disabled:cursor-not-allowed disabled:text-fg-muted disabled:opacity-60 disabled:hover:bg-transparent [&>svg]:row-span-2"
          >
            {RECIPIENT_ICON}
            <span>Recipient unavailable</span>
            <span className="text-[11px] text-fg-muted">
              {recipient.busy
                ? 'Triggering…'
                : canMarkRecipient
                  ? 'Fail a delivery on arrival'
                  : 'No delivery on its way'}
            </span>
          </button>
        </li>
        <li>
          <button
            type="button"
            disabled={lprActive || lprAction.busy}
            title={
              lprActive
                ? 'An LPR helicopter is already crossing the area'
                : 'Start the LPR helicopter'
            }
            onClick={startLpr}
            className="grid min-h-10 w-full grid-cols-[auto_1fr] items-center gap-x-3 rounded border border-line px-2 py-1.5 text-left text-xs text-fg hover:bg-surface-raised disabled:cursor-not-allowed disabled:text-fg-muted disabled:opacity-60 disabled:hover:bg-transparent [&>svg]:row-span-2"
          >
            {LPR_ICON}
            <span>LPR helicopter</span>
            <span className="text-[11px] text-fg-muted">
              {lprAction.busy
                ? 'Triggering…'
                : lprActive
                  ? 'Helicopter in transit'
                  : 'Cross the area'}
            </span>
          </button>
        </li>
        <li>
          <button
            type="button"
            disabled={rainAction.busy}
            aria-pressed={rainWarningActive}
            title={
              rainWarningActive
                ? 'Clear the rain warning: new takeoffs are allowed again'
                : 'Suspend new takeoffs (flights in the air continue)'
            }
            onClick={toggleRainWarning}
            className={`grid min-h-10 w-full grid-cols-[auto_1fr] items-center gap-x-3 rounded border px-2 py-1.5 text-left text-xs text-fg hover:bg-surface-raised disabled:cursor-not-allowed disabled:opacity-60 [&>svg]:row-span-2 ${
              rainWarningActive ? 'border-status-warning bg-status-warning/15' : 'border-line'
            }`}
          >
            {RAIN_ICON}
            <span>{rainWarningActive ? 'Clear Rain Warning' : 'Activate Rain Warning'}</span>
            <span className="text-[11px] text-fg-muted">
              {rainAction.busy
                ? 'Updating…'
                : rainWarningActive
                  ? 'Active: takeoffs suspended'
                  : 'Precautionary grounding'}
            </span>
          </button>
        </li>
      </ul>
      {confirming && (
        <CancelConfirmation
          order={selectedOrder}
          busy={cancellation.busy}
          onConfirm={confirm}
          onKeep={() => setConfirmingId(null)}
        />
      )}
      {failure.error && (
        <p role="alert" className="mt-2 text-xs text-status-critical">
          {failure.error}
        </p>
      )}
      {rainAction.error && (
        <p role="alert" className="mt-2 text-xs text-status-critical">
          {rainAction.error}
        </p>
      )}
      {lprAction.error && (
        <p role="alert" className="mt-2 text-xs text-status-critical">
          {lprAction.error}
        </p>
      )}
      {lprNote && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          {lprNote}
        </p>
      )}
      {recipient.error && (
        <p role="alert" className="mt-2 text-xs text-status-critical">
          {recipient.error}
        </p>
      )}
      {recipientNote && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          {recipientNote.text}
        </p>
      )}
      {failureNote && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          {failureNote.text}
        </p>
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
