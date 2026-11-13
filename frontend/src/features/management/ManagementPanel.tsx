import { useEffect, useState, type ReactNode } from 'react'

import { SECONDARY_BUTTON_CLASS } from './formStyles'

export interface ManagementTab {
  id: string
  label: string
  content: ReactNode
}

interface ManagementPanelProps {
  tabs: readonly ManagementTab[]
  onClose: () => void
}

/**
 * The Management area: an overlay above the map (which stays mounted, so polling, flights and the
 * worker are unaffected) with one tab per managed resource.
 */
export function ManagementPanel({ tabs, onClose }: ManagementPanelProps) {
  const [activeId, setActiveId] = useState(tabs[0]?.id)
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0]

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-label="Management"
      className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-canvas/95 sm:inset-3 sm:rounded-lg sm:border sm:border-line"
    >
      <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-2">
        <div role="tablist" aria-label="Management sections" className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={tab.id === active?.id}
              className={`rounded px-3 py-1.5 text-sm ${
                tab.id === active?.id ? 'bg-surface-raised text-fg' : 'text-fg-muted hover:text-fg'
              }`}
              onClick={() => setActiveId(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button type="button" className={SECONDARY_BUTTON_CLASS} onClick={onClose}>
          Close
        </button>
      </div>
      <div role="tabpanel" className="min-h-0 flex-1 overflow-y-auto p-4">
        {active?.content}
      </div>
    </div>
  )
}
