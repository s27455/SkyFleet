import { useEffect } from 'react'

import type { Hub } from '../../types/hub'

interface HubDetailPanelProps {
  hub: Hub
  onClose: () => void
}

export function HubDetailPanel({ hub, onClose }: HubDetailPanelProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <aside
      aria-label={`Hub details: ${hub.name}`}
      className="absolute inset-x-3 bottom-3 z-20 rounded-lg border border-line bg-surface p-4 shadow-lg sm:inset-x-auto sm:top-3 sm:bottom-auto sm:left-3 sm:w-80"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{hub.name}</h2>
          <p className="text-sm text-fg-muted">{hub.address}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close hub details"
          className="-mt-1 -mr-1 inline-flex size-10 items-center justify-center rounded-md text-fg-muted hover:bg-surface-raised hover:text-fg focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      <dl className="mt-3 space-y-2 text-sm">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-fg-muted">Maximum drone capacity</dt>
          <dd className="font-mono tabular-nums">{hub.droneCapacity}</dd>
        </div>
      </dl>

      <p className="mt-3 border-t border-line pt-3 text-xs text-fg-muted">
        Illustrative mall location, not a real SkyFleet facility.
      </p>
    </aside>
  )
}
