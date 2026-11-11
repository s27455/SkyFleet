import type { Hub } from '../../types/hub'
import type { Order } from '../../types/order'
import { ORDER_STATUS_DISPLAY } from '../orders/orderStatus'
import { type PixelOffset, computeRingOffsets } from './droneMarkers'

const ORDER_MARKER_SIZE_PX = 24

/** Ring offsets for destination markers that share an exact point (display only). */
export function computeOrderOffsets(
  orders: readonly Order[],
  hubs: readonly Hub[],
): ReadonlyMap<string, PixelOffset> {
  return computeRingOffsets(orders, hubs, ORDER_MARKER_SIZE_PX)
}

export function orderMarkerLabel(order: Order) {
  return `Order ${order.id} destination, ${ORDER_STATUS_DISPLAY[order.status].label}, ${order.packageWeightKg} kg`
}

// The button is a transparent 24px target with a visible focus ring; the diamond inside is the mark.
// z-5 keeps destinations below Hub (z-10) and drone (z-20) markers.
const ORDER_MARKER_CLASS =
  'z-5 flex size-6 cursor-pointer items-center justify-center bg-transparent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'
const DIAMOND_CLASS = 'size-3 rotate-45 border-2 shadow'
const DIAMOND_IDLE_CLASSES = ['bg-surface', 'border-fg-muted']
// The ring is a second, non-colour selection cue.
const DIAMOND_SELECTED_CLASSES = ['bg-accent', 'border-fg', 'ring-4', 'ring-accent/40']

export function createOrderMarkerElement(order: Order, onClick: () => void) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = ORDER_MARKER_CLASS
  element.dataset.markerKind = 'order'
  element.setAttribute('aria-label', orderMarkerLabel(order))
  const diamond = document.createElement('span')
  diamond.dataset.orderDiamond = ''
  diamond.setAttribute('aria-hidden', 'true')
  diamond.className = DIAMOND_CLASS
  element.appendChild(diamond)
  element.addEventListener('click', onClick)
  setOrderMarkerSelected(element, false)
  return element
}

/** Updates the existing element in place so keyboard focus survives a selection change. */
export function setOrderMarkerSelected(element: HTMLElement, selected: boolean) {
  const diamond = element.querySelector<HTMLElement>('[data-order-diamond]')
  diamond?.classList.remove(...(selected ? DIAMOND_IDLE_CLASSES : DIAMOND_SELECTED_CLASSES))
  diamond?.classList.add(...(selected ? DIAMOND_SELECTED_CLASSES : DIAMOND_IDLE_CLASSES))
  element.setAttribute('aria-pressed', String(selected))
}
