import type { HubsState } from './useHubs'

interface HubsStatusBannerProps {
  state: HubsState
  onRetry: () => void
}

const BANNER_CLASS =
  'absolute inset-x-3 top-3 z-20 rounded-lg border border-line bg-surface p-3 text-sm text-fg-muted shadow-lg sm:inset-x-auto sm:right-3 sm:w-80'

/** Non-blocking overlay for the Hub data lifecycle; the map underneath stays usable. */
export function HubsStatusBanner({ state, onRetry }: HubsStatusBannerProps) {
  if (state.status === 'loading') {
    return (
      <div role="status" className={BANNER_CLASS}>
        Loading hubs…
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div role="alert" className={BANNER_CLASS}>
        <p className="font-medium text-fg">Hub data is unavailable</p>
        <p className="mt-1">The backend could not be reached or returned invalid data.</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 inline-flex min-h-10 items-center rounded-md border border-line px-3 text-fg hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
        >
          Retry
        </button>
      </div>
    )
  }

  if (state.hubs.length === 0) {
    return (
      <div role="status" className={BANNER_CLASS}>
        No hubs are available yet.
      </div>
    )
  }

  return null
}
