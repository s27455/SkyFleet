import { formatUtcTimestamp } from '../orders/orderStatus'
import type { EventOrigin, EventType } from '../../types/event'
import { SECONDARY_BUTTON_CLASS } from '../management/formStyles'
import { useOrderEvents } from './useOrderEvents'

const EVENT_DESCRIPTIONS: Record<EventType, string> = {
  ORDER_CREATED: 'Order created',
  ORDER_CANCELLED: 'Order cancelled',
  DRONE_FAILURE: 'Drone failure',
  RECIPIENT_UNAVAILABLE: 'Recipient unavailable',
  LPR_TRANSIT: 'LPR helicopter in transit',
}

const ORIGIN_LABELS: Record<EventOrigin, string> = {
  SYSTEM: 'System',
  AUTOMATIC: 'Automatic',
  MANUAL: 'Manual',
}

/**
 * Chronological Activity timeline of one order, from the persisted backend events. It shows only
 * what the backend recorded: an order that predates event recording simply has no events.
 */
export function EventTimeline({ orderId }: { orderId: string }) {
  const { state, stale, retry } = useOrderEvents(orderId)

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
        <p className="mt-1 text-xs text-fg-muted">No recorded activity for this order.</p>
      )}
      {state.status === 'ready' && state.data.length > 0 && (
        <ol className="mt-2 space-y-2 text-sm">
          {state.data.map((event) => (
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
