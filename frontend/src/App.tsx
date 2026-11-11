import { MapView } from './features/map/MapView'
import { BackendStatus } from './features/system-status/BackendStatus'

function App() {
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
        <MapView />
      </main>
    </div>
  )
}

export default App
