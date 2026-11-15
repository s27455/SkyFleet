import type { Hub } from '../../types/hub'

interface HubsListProps {
  hubs: readonly Hub[]
  /** Drones docked at each Hub (by Hub id). */
  dockedCounts: ReadonlyMap<string, number>
  selectedHubId: string | null
  onSelectHub: (hubId: string) => void
}

/** Every Hub as a selectable row (the Hubs tab). Selecting opens the usual Hub details. */
export function HubsList({ hubs, dockedCounts, selectedHubId, onSelectHub }: HubsListProps) {
  if (hubs.length === 0) return <p className="p-3 text-xs text-fg-muted">No Hubs.</p>

  return (
    <ul aria-label="Hubs">
      {hubs.map((hub) => {
        const selected = hub.id === selectedHubId
        return (
          <li key={hub.id}>
            <button
              type="button"
              aria-pressed={selected}
              onClick={() => onSelectHub(hub.id)}
              className={`flex min-h-10 w-full flex-col gap-0.5 border-l-4 px-3 py-2 text-left hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent ${
                selected ? 'border-accent bg-surface-raised' : 'border-transparent'
              }`}
            >
              <span className="flex items-center justify-between gap-3">
                <span className="font-medium">{hub.name}</span>
                <span className="text-fg-muted">
                  {dockedCounts.get(hub.id) ?? 0} / {hub.droneCapacity} drones
                </span>
              </span>
              <span className="text-xs text-fg-muted">{hub.address}</span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
