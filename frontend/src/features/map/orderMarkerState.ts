import type { OrderStatus } from '../../types/order'

/** What a destination marker tells the operator. Styling lives apart, in `ORDER_MARKER_STATES`. */
export type OrderMarkerState = 'pending' | 'in_progress' | 'delivered' | 'cancelled' | 'other'

/**
 * Backend order status to marker state, written out for every status (Feature 017B). Only the
 * order status decides: an order whose mission is merely assigned is still READY_FOR_PICKUP and
 * stays "waiting" until takeoff. When the backend adds a status, TypeScript flags this table.
 */
const STATE_BY_STATUS: Record<OrderStatus, OrderMarkerState> = {
  CREATED: 'pending',
  AWAITING_HANDOVER: 'pending',
  READY_FOR_PICKUP: 'pending',
  OUT_FOR_DELIVERY: 'in_progress',
  DELIVERED: 'delivered',
  CANCELLED: 'cancelled',
}

/** A status this build does not know (a newer backend) is shown neutrally, never guessed. */
export function orderMarkerState(status: string): OrderMarkerState {
  return Object.hasOwn(STATE_BY_STATUS, status) ? STATE_BY_STATUS[status as OrderStatus] : 'other'
}

export interface OrderMarkerStyle {
  /** Short text for the legend and the marker's accessible name (never colour alone). */
  label: string
  /** Fill and outline classes of the diamond when the marker is not selected. */
  diamondClasses: readonly string[]
  /** Legend swatch fill. */
  swatchClass: string
}

export const ORDER_MARKER_STATES: Record<OrderMarkerState, OrderMarkerStyle> = {
  pending: {
    label: 'Waiting',
    diamondClasses: ['bg-status-neutral', 'border-fg'],
    swatchClass: 'bg-status-neutral',
  },
  in_progress: {
    label: 'In delivery',
    diamondClasses: ['bg-status-active', 'border-fg'],
    swatchClass: 'bg-status-active',
  },
  delivered: {
    label: 'Delivered',
    diamondClasses: ['bg-status-ok', 'border-fg'],
    swatchClass: 'bg-status-ok',
  },
  cancelled: {
    label: 'Cancelled',
    diamondClasses: ['bg-status-critical', 'border-fg'],
    swatchClass: 'bg-status-critical',
  },
  other: {
    label: 'Other',
    diamondClasses: ['bg-surface', 'border-fg-muted'],
    swatchClass: 'bg-surface',
  },
}
