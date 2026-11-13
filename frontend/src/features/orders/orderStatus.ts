import type { StatusTone } from '../../components/ui/StatusIndicator'
import type { OrderStatus } from '../../types/order'

/** Backend status as readable text (always shown as text, never by colour alone). */
export const ORDER_STATUS_DISPLAY: Record<OrderStatus, { tone: StatusTone; label: string }> = {
  CREATED: { tone: 'neutral', label: 'Created' },
  AWAITING_HANDOVER: { tone: 'warning', label: 'Awaiting handover' },
  READY_FOR_PICKUP: { tone: 'ok', label: 'Ready for pickup' },
  OUT_FOR_DELIVERY: { tone: 'warning', label: 'Out for delivery' },
  DELIVERED: { tone: 'neutral', label: 'Delivered' },
  CANCELLED: { tone: 'critical', label: 'Cancelled' },
  DELIVERY_FAILED: { tone: 'warning', label: 'Delivery failed' },
}

/** Order states the operator may try to cancel; the backend makes the final decision. */
export const CANCELLABLE_STATUSES: readonly OrderStatus[] = [
  'CREATED',
  'AWAITING_HANDOVER',
  'READY_FOR_PICKUP',
  'OUT_FOR_DELIVERY',
]

export const isCancellable = (order: { status: OrderStatus }) =>
  CANCELLABLE_STATUSES.includes(order.status)

const UTC_FORMAT = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
})

/** Timestamps are shown in UTC with an explicit label, so no local time zone is implied. */
export function formatUtcTimestamp(iso: string) {
  return `${UTC_FORMAT.format(new Date(iso))} UTC`
}
