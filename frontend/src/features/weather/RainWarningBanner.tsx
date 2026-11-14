interface RainWarningBannerProps {
  /** True when the warning is active. Nothing is rendered otherwise. */
  active: boolean
  /** True when the last refresh failed, so the state shown may be out of date. */
  stale?: boolean
}

/**
 * A slim global notice. It states the precaution, not a measurement: SkyFleet has no live weather
 * data. Flights already in the air continue; only NEW takeoffs are suspended.
 */
export function RainWarningBanner({ active, stale = false }: RainWarningBannerProps) {
  if (!active) return null
  return (
    <div
      role="status"
      aria-label="Rain warning"
      className="flex flex-wrap items-center gap-x-3 border-b border-line bg-status-warning/15 px-4 py-1.5 text-sm sm:px-6"
    >
      <strong className="font-semibold">Rain warning</strong>
      <span>New takeoffs suspended (precautionary). Flights in the air continue.</span>
      {stale && <span className="text-fg-muted">Status may be out of date.</span>}
    </div>
  )
}
