import { useEffect, useRef } from 'react'

import { formatUtcTimestamp } from '../orders/orderStatus'
import type { EventOrigin, EventType } from '../../types/event'
import { SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { useDroneEvents, useOrderEvents } from './useOrderEvents'

const EVENT_DESCRIPTIONS: Record<EventType, string> = {
  ORDER_CREATED: 'Order created',
  ORDER_CANCELLED: 'Order cancelled',
  DRONE_FAILURE: 'Drone failure',
  RECIPIENT_UNAVAILABLE: 'Recipient unavailable',
  LPR_TRANSIT: 'LPR helicopter in transit',
  DRONE_RELOCATION: 'Drone relocation',
  RAIN_WARNING_ACTIVATED: 'Rain warning activated',
  RAIN_WARNING_CLEARED: 'Rain warning cleared',
}

const ORIGIN_LABELS: Record<EventOrigin, string> = {
  SYSTEM: 'System',
  AUTOMATIC: 'Automatic',
  MANUAL: 'Manual',
}

type EventTimelineProps = { refreshKey?: number } & (
  { orderId: string; droneId?: undefined } | { droneId: string; orderId?: undefined }
)

/**
 * Chronological Activity timeline of one order, or of one drone (Feature 019A: a relocation has no
 * order), from the persisted backend events. It shows only what the backend recorded: an order
 * that predates event recording simply has no events.
 */
export function EventTimeline(props: EventTimelineProps) {
  // Changes when something happened to the order or drone: read the events again now.
  const { refreshKey = 0 } = props
  return props.droneId === undefined ? (
    <OrderActivity orderId={props.orderId} refreshKey={refreshKey} />
  ) : (
    <DroneActivity droneId={props.droneId} refreshKey={refreshKey} />
  )
}

function OrderActivity({ orderId, refreshKey }: { orderId: string; refreshKey: number }) {
  return <Timeline resource={useOrderEvents(orderId)} refreshKey={refreshKey} subject="order" />
}

/** A drone's panel shows only its latest events, newest first; the history stays in the backend. */
export const DRONE_ACTIVITY_LIMIT = 3

function DroneActivity({ droneId, refreshKey }: { droneId: string; refreshKey: number }) {
  return (
    <Timeline
      resource={useDroneEvents(droneId)}
      refreshKey={refreshKey}
      subject="drone"
      newestFirstLimit={DRONE_ACTIVITY_LIMIT}
    />
  )
}

function Timeline({
  resource,
  refreshKey,
  subject,
  newestFirstLimit,
}: {
  resource: ReturnType<typeof useOrderEvents>
  refreshKey: number
  subject: 'order' | 'drone'
  newestFirstLimit?: number
}) {
  const { state, stale, retry, refresh } = resource
  const firstKey = useRef(refreshKey)
  useEffect(() => {
    if (refreshKey !== firstKey.current) refresh()
  }, [refreshKey, refresh])

  // Recency is the backend's own order: occurred_at, then id (a tie shows the later record first).
  const events =
    state.status === 'ready' && newestFirstLimit !== undefined
      ? [...state.data]
          .sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt) || b.id - a.id)
          .slice(0, newestFirstLimit)
      : state.status === 'ready'
        ? state.data
        : []

  return (
    <section aria-label="Activity" className="mt-3 border-t border-line pt-3">
      <h3 className="text-sm font-semibold">Activity</h3>
      {state.status === 'loading' && (
        <p role="status" className="mt-1 text-xs text-fg-muted">
          Loading activity…
        </p>
      )}
      {state.status === 'error' && (
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          Activity unavailable
          <button type="button" className={SECONDARY_BUTTON_CLASS} onClick={retry}>
            Retry activity
          </button>
        </p>
      )}
      {state.status === 'ready' && state.data.length === 0 && (
        <p className="mt-1 text-xs text-fg-muted">No recorded activity for this {subject}.</p>
      )}
      {state.status === 'ready' && state.data.length > 0 && (
        <ol className="mt-2 space-y-2 text-sm">
          {events.map((event) => (
            <li key={event.id}>
              <p>{EVENT_DESCRIPTIONS[event.type]}</p>
              <p className="text-xs text-fg-muted">
                <time dateTime={event.occurredAt}>{formatUtcTimestamp(event.occurredAt)}</time>
                {' · '}
                {ORIGIN_LABELS[event.origin]}
                {event.missionId && ` · Mission ${event.missionId}`}
                {event.droneId && ` · Drone ${event.droneId}`}
              </p>
              {event.reason && <p className="text-xs text-fg-muted">{event.reason}</p>}
            </li>
          ))}
        </ol>
      )}
      {state.status === 'ready' && stale && (
        <p role="status" className="mt-1 text-xs text-fg-muted">
          Showing the last loaded activity; refreshing failed.
        </p>
      )}
    </section>
  )
}
