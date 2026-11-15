import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from 'react'

import { OPERATIONS_TABS, type OperationsTab } from './tabs'

interface OperationsPanelProps {
  tab: OperationsTab
  onTabChange: (tab: OperationsTab) => void
  /** Tab labels may carry a count, e.g. "Orders (10)". */
  labels: Record<OperationsTab, string>
  /** The content of the active tab; the caller renders only what the active tab needs. */
  children: ReactNode
  /**
   * Hides the panel on narrow screens (it stays mounted, so its open state survives) while a detail
   * panel is open: both together would cover most of a phone-sized map.
   */
  hideOnNarrow?: boolean
}

/**
 * The map-adjacent operational panel: Drones, Hubs, Orders and Events behind one collapsible header
 * (closed by default so it does not cover the map). The tab is controlled by the caller, so the map
 * selection can pick it even while the panel is closed; opening it never changes the selection.
 * Height is bounded and the content scrolls inside the panel (Feature 021B).
 */
export function OperationsPanel({
  tab,
  onTabChange,
  labels,
  children,
  hideOnNarrow = false,
}: OperationsPanelProps) {
  const [open, setOpen] = useState(false)
  const baseId = useId()
  const tabRefs = useRef<Partial<Record<OperationsTab, HTMLButtonElement | null>>>({})

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = OPERATIONS_TABS.indexOf(tab)
    let next: number | null = null
    if (event.key === 'ArrowRight') next = (index + 1) % OPERATIONS_TABS.length
    if (event.key === 'ArrowLeft') {
      next = (index - 1 + OPERATIONS_TABS.length) % OPERATIONS_TABS.length
    }
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = OPERATIONS_TABS.length - 1
    if (next === null) return
    event.preventDefault()
    const target = OPERATIONS_TABS[next]
    onTabChange(target)
    tabRefs.current[target]?.focus()
  }

  return (
    <section
      aria-label="Operations"
      className={`flex min-h-0 shrink flex-col rounded-lg border border-line bg-surface text-sm shadow-lg ${
        hideOnNarrow ? 'max-sm:hidden' : ''
      }`}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? `${baseId}-panel` : undefined}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-10 w-full shrink-0 items-center justify-between gap-3 rounded-lg px-3 text-left font-medium hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span>Operations</span>
        <span aria-hidden="true" className="text-fg-muted">
          {open ? '▴' : '▾'}
        </span>
      </button>

      {open && (
        <>
          <div
            role="tablist"
            aria-label="Operations sections"
            onKeyDown={onKeyDown}
            className="flex shrink-0 gap-1 overflow-x-auto border-t border-line px-2 py-1"
          >
            {OPERATIONS_TABS.map((id) => (
              <button
                key={id}
                ref={(element) => {
                  tabRefs.current[id] = element
                }}
                id={`${baseId}-tab-${id}`}
                type="button"
                role="tab"
                aria-selected={id === tab}
                aria-controls={`${baseId}-panel`}
                tabIndex={id === tab ? 0 : -1}
                onClick={() => onTabChange(id)}
                className={`min-h-9 shrink-0 rounded px-3 text-xs whitespace-nowrap focus-visible:outline-2 focus-visible:outline-accent ${
                  id === tab ? 'bg-surface-raised text-fg' : 'text-fg-muted hover:text-fg'
                }`}
              >
                {labels[id]}
              </button>
            ))}
          </div>
          <div
            id={`${baseId}-panel`}
            role="tabpanel"
            aria-labelledby={`${baseId}-tab-${tab}`}
            className="max-h-[40dvh] min-h-0 overflow-y-auto overscroll-contain border-t border-line sm:max-h-[60dvh]"
          >
            {children}
          </div>
        </>
      )}
    </section>
  )
}
