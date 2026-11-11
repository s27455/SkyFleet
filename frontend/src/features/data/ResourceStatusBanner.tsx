import type { ResourceState } from './useApiResource'

interface ResourceStatusBannerProps {
  /** Singular noun used in messages and the Retry label, e.g. "hub" or "drone". */
  resource: string
  state: ResourceState<readonly unknown[]>
  onRetry: () => void
}

const BANNER_CLASS = 'rounded-lg border border-line bg-surface p-3 text-sm text-fg-muted shadow-lg'

/** Non-blocking notice for one backend resource's lifecycle; the map underneath stays usable. */
export function ResourceStatusBanner({ resource, state, onRetry }: ResourceStatusBannerProps) {
  if (state.status === 'loading') {
    return (
      <div role="status" className={BANNER_CLASS}>
        Loading {resource}s…
      </div>
    )
  }

  if (state.status === 'error') {
    const name = resource.charAt(0).toUpperCase() + resource.slice(1)
    return (
      <div role="alert" className={BANNER_CLASS}>
        <p className="font-medium text-fg">{name} data is unavailable</p>
        <p className="mt-1">The backend could not be reached or returned invalid data.</p>
        <button
          type="button"
          onClick={onRetry}
          aria-label={`Retry loading ${resource}s`}
          className="mt-3 inline-flex min-h-10 items-center rounded-md border border-line px-3 text-fg hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
        >
          Retry
        </button>
      </div>
    )
  }

  if (state.data.length === 0) {
    return (
      <div role="status" className={BANNER_CLASS}>
        No {resource}s are available yet.
      </div>
    )
  }

  return null
}
