import { useCallback, useState } from 'react'

import { HubDetailPanel } from './features/hubs/HubDetailPanel'
import { getHubs } from './features/hubs/mockHubs'
import { MapView } from './features/map/MapView'
import { BackendStatus } from './features/system-status/BackendStatus'

const hubs = getHubs()

function App() {
  const [selectedHubId, setSelectedHubId] = useState<string | null>(null)
  const selectedHub = hubs.find((hub) => hub.id === selectedHubId)
  const clearSelection = useCallback(() => setSelectedHubId(null), [])

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">
            Sky<span className="text-accent">Fleet</span>
          </h1>
          <span className="hidden text-sm text-fg-muted sm:inline">Operations Center</span>
        </div>
        <BackendStatus />
      </header>

      <main className="relative min-h-0 flex-1">
        <MapView hubs={hubs} selectedHubId={selectedHubId} onSelectHub={setSelectedHubId} />
        {selectedHub && <HubDetailPanel hub={selectedHub} onClose={clearSelection} />}
      </main>
    </div>
  )
}

export default App
