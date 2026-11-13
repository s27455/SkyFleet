import { ORDER_MARKER_STATES, type OrderMarkerState } from './orderMarkerState'

// The states an operator can meet; "other" (an unknown status) is not worth a legend row.
const LEGEND_STATES: readonly OrderMarkerState[] = [
  'pending',
  'in_progress',
  'delivered',
  'cancelled',
  'interrupted',
  'delivery_failed',
]

interface OrderMarkerLegendProps {
  /** Adds the emergency landing marker to the key while one is on the map (Feature 018C). */
  showEmergency?: boolean
  /** Hidden on narrow screens while a details panel covers the bottom of the map. */
  hideOnNarrow?: boolean
}

/** Compact key for the delivery-address diamonds: a swatch and a word per state. */
export function OrderMarkerLegend({
  hideOnNarrow = false,
  showEmergency = false,
}: OrderMarkerLegendProps) {
  return (
    <section
      aria-label="Delivery marker legend"
      className={`absolute bottom-9 left-3 z-10 rounded-lg border border-line bg-surface/90 px-3 py-2 text-xs text-fg-muted shadow-lg ${
        hideOnNarrow ? 'hidden sm:block' : ''
      }`}
    >
      <p className="mb-1 font-medium text-fg">Deliveries</p>
      <ul className="flex flex-col gap-1">
        {LEGEND_STATES.map((state) => (
          <li key={state} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={`size-2.5 rotate-45 border border-fg ${ORDER_MARKER_STATES[state].swatchClass}`}
            />
            {ORDER_MARKER_STATES[state].label}
          </li>
        ))}
        {showEmergency && (
          <li className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="flex size-3 items-center justify-center rounded-full border border-fg bg-status-critical text-[8px] leading-none font-bold text-canvas"
            >
              ✕
            </span>
            Emergency landing
          </li>
        )}
      </ul>
    </section>
  )
}
