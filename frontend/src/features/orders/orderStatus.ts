import type { StatusTone } from '../../components/ui/StatusIndicator'
import type { OrderStatus } from '../../types/order'

/** Backend status as readable text (always shown as text, never by colour alone). */
export const ORDER_STATUS_DISPLAY: Record<OrderStatus, { tone: StatusTone; label: string }> = {
  CREATED: { tone: 'neutral', label: 'Created' },
  AWAITING_HANDOVER: { tone: 'warning', label: 'Awaiting handover' },
  READY_FOR_PICKUP: { tone: 'ok', label: 'Ready for pickup' },
}

const UTC_FORMAT = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
})

/** Timestamps are shown in UTC with an explicit label, so no local time zone is implied. */
export function formatUtcTimestamp(iso: string) {
  return `${UTC_FORMAT.format(new Date(iso))} UTC`
}
