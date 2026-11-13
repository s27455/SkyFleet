import { type ReactNode, useEffect } from 'react'

import { DETAIL_PANEL_CLASS } from '../../components/ui/detailPanel'
import { StatusIndicator } from '../../components/ui/StatusIndicator'
import type { Flight } from '../../types/flight'
import type { Hub } from '../../types/hub'
import type { Mission } from '../../types/mission'
import type { Order } from '../../types/order'
import { EventTimeline } from '../events/EventTimeline'
import { FlightSection } from '../flights/FlightSection'
import { isRecipientPending } from '../flights/flightStatus'
import { StartMissionControl } from '../missions/StartMissionControl'
import { CancelOrderAction } from './CancelOrderAction'
import { ORDER_STATUS_DISPLAY, formatUtcTimestamp } from './orderStatus'

interface OrderDetailPanelProps {
  order: Order
  /** The origin Hub if the Hub data is available; otherwise the Hub id is shown as is. */
  hub?: Hub
  /** True when the destination marker is spread on screen because orders share this location. */
  markerSpread: boolean
  onClose: () => void
  /** An `ASSIGNED` mission for this order, which can be started from here. */
  assignedMission?: Mission
  /** The Hubs, to name the mission's planned return Hub. */
  hubs?: readonly Hub[]
  onStartMission?: (missionId: string) => Promise<void>
  /** Shows the Cancel order action; called after every answer so the views are re-read. */
  onCancelled?: () => void
  /** The order's active flight, if any: shown once the order was cancelled and the drone recalled. */
  flight?: Flight
  workerStale?: boolean
  /** Changes after a cancellation so the Activity timeline is re-read at once. */
  activityRefreshKey?: number
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

export function OrderDetailPanel({
  order,
  hub,
  markerSpread,
  onClose,
  assignedMission,
  hubs = [],
  onStartMission,
  onCancelled,
  flight,
  workerStale = false,
  activityRefreshKey = 0,
}: OrderDetailPanelProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const status = ORDER_STATUS_DISPLAY[order.status]
  // A drone failure (Feature 018C) interrupts an undelivered delivery without changing the order
  // status, so the interruption comes from the order's flight.
  const failed = flight?.failedAt != null
  const interrupted = failed && flight?.deliveredAt === null && order.status === 'OUT_FOR_DELIVERY'
  const grounded = flight?.phase === 'EMERGENCY'
  // Feature 018E: a drone that could not afford to wait for the LPR helicopter ends in the existing
  // battery emergency before the handover. It is not a drone failure, so it is said differently.
  const batteryEmergency =
    flight?.phase === 'EMERGENCY' &&
    !failed &&
    flight.deliveredAt === null &&
    flight.recalledAt === null &&
    flight.handoverFailedAt === null &&
    order.status === 'OUT_FOR_DELIVERY'
  // Feature 018D: "recipient unavailable" is pending until the drone reaches the destination; after
  // that the order itself is DELIVERY_FAILED (a real status, unlike an interruption).
  const pendingRecipient =
    flight !== undefined && order.status === 'OUT_FOR_DELIVERY' && isRecipientPending(flight)
  const deliveryFailed = order.status === 'DELIVERY_FAILED'
  const [longitude, latitude] = order.coordinates

  return (
    <aside aria-label={`Order details: ${order.id}`} className={DETAIL_PANEL_CLASS}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{order.id}</h2>
          <p className="text-sm text-fg-muted">Delivery order</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close order details"
          className="-mt-1 -mr-1 inline-flex size-10 items-center justify-center rounded-md text-fg-muted hover:bg-surface-raised hover:text-fg focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      <dl className="mt-3 space-y-2 text-sm">
        <Row label="Status">
          <StatusIndicator tone={status.tone} label={status.label} />
        </Row>
        <Row label="Package weight">
          <span className="font-mono tabular-nums">{order.packageWeightKg} kg</span>
        </Row>
        <Row label="Origin Hub">{hub ? hub.name : order.originHubId}</Row>
        <Row label="Destination">{order.destinationAddress}</Row>
        <Row label="Destination position">
          <span className="font-mono text-xs tabular-nums">
            {latitude.toFixed(6)}, {longitude.toFixed(6)}
          </span>
        </Row>
        <Row label="Created">{formatUtcTimestamp(order.createdAt)}</Row>
        <Row label="Updated">{formatUtcTimestamp(order.updatedAt)}</Row>
        {order.cancelledAt && <Row label="Cancelled">{formatUtcTimestamp(order.cancelledAt)}</Row>}
        {order.deliveryFailedAt && (
          <Row label="Delivery failed">{formatUtcTimestamp(order.deliveryFailedAt)}</Row>
        )}
      </dl>

      {onCancelled && !interrupted && !batteryEmergency && !deliveryFailed && (
        <CancelOrderAction order={order} onCancelled={onCancelled} />
      )}

      {order.status === 'CANCELLED' && (
        <p
          role="status"
          className="mt-3 rounded border border-status-critical p-2 text-xs text-status-critical"
        >
          This order was cancelled
          {order.cancelledAt ? ` at ${formatUtcTimestamp(order.cancelledAt)}` : ''}.
          {failed
            ? ' The recalled drone then failed; the cancellation did not repair it.'
            : flight?.recalledAt
              ? ' The drone was recalled and is returning with the parcel.'
              : ' No flight is active for it.'}
        </p>
      )}
      {order.status === 'CANCELLED' && (flight?.recalledAt || failed) && flight && (
        <FlightSection flight={flight} hubs={hubs} workerStale={workerStale} />
      )}
      {pendingRecipient && flight && (
        <>
          <p
            role="status"
            className="mt-3 rounded border border-status-failed p-2 text-xs text-status-failed"
          >
            Recipient unavailable reported. Drone {flight.droneId} is still flying to the
            destination; the delivery fails when it arrives. Until then the order stays out for
            delivery.
          </p>
          <FlightSection flight={flight} hubs={hubs} workerStale={workerStale} />
        </>
      )}
      {deliveryFailed && (
        <>
          <p
            role="status"
            className="mt-3 rounded border border-status-failed p-2 text-xs text-status-failed"
          >
            Delivery failed: the recipient was unavailable
            {order.deliveryFailedAt ? ` at ${formatUtcTimestamp(order.deliveryFailedAt)}` : ''}. The
            parcel was not delivered
            {flight && flight.phase !== 'LANDED' && flight.handoverFailedAt
              ? `; drone ${flight.droneId} is returning with it.`
              : ' and was brought back to a Hub.'}
          </p>
          <p className="mt-2 text-xs text-fg-muted">
            Cancelling is not available: the delivery attempt has already failed.
          </p>
          {flight && flight.handoverFailedAt && (
            <FlightSection flight={flight} hubs={hubs} workerStale={workerStale} />
          )}
        </>
      )}
      {batteryEmergency && flight && (
        <>
          <p
            role="status"
            className="mt-3 rounded border border-status-critical p-2 text-xs text-status-critical"
          >
            Delivery interrupted: drone {flight.droneId} made an emergency landing because its
            battery would have fallen below the critical level, and is grounded, requiring service;
            the parcel was not delivered.
          </p>
          <FlightSection flight={flight} hubs={hubs} workerStale={workerStale} />
        </>
      )}
      {interrupted && flight && (
        <>
          <p
            role="status"
            className="mt-3 rounded border border-status-critical p-2 text-xs text-status-critical"
          >
            Delivery interrupted by drone failure. Drone {flight.droneId}{' '}
            {grounded ? 'is grounded, requiring service' : 'is making an emergency landing'}; the
            parcel was not delivered.
          </p>
          <p className="mt-2 text-xs text-fg-muted">
            Cancelling is not available for this order: it would not repair or recall the drone.
          </p>
          <FlightSection flight={flight} hubs={hubs} workerStale={workerStale} />
        </>
      )}

      {assignedMission && onStartMission && (
        <StartMissionControl
          mission={assignedMission}
          returnHubName={
            hubs.find((candidate) => candidate.id === assignedMission.returnHubId)?.name
          }
          onStart={onStartMission}
        />
      )}

      <EventTimeline orderId={order.id} refreshKey={activityRefreshKey} />

      <p className="mt-3 border-t border-line pt-3 text-xs text-fg-muted">
        Simulation data: the destination is illustrative, not a verified customer address.
        {markerSpread &&
          ' Markers at the same location are spread slightly on screen; the position above is the real stored one.'}
      </p>
    </aside>
  )
}
