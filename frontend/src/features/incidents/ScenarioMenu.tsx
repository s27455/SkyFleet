import { useCallback, useEffect, useId, useRef, useState } from 'react'

import { type SimulationEventsPanelProps, SimulationEventsPanel } from './SimulationEventsPanel'

/**
 * One "Scenarios" button in the header that opens a compact, bounded menu of the manual simulation
 * events (the existing `SimulationEventsPanel`, with its confirmations, validation and feedback).
 *
 * The panel stays mounted while the menu is closed, so a confirmation or a result is not lost by
 * closing it. Escape and an outside click close the menu, except while an action is waiting for the
 * operator's confirmation or the backend's answer: that cannot be dismissed by accident (the
 * button itself still toggles the menu).
 */
export function ScenarioMenu(props: Omit<SimulationEventsPanelProps, 'onPendingChange'>) {
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()
  const onPendingChange = useCallback((value: boolean) => setPending(value), [])

  useEffect(() => {
    if (!open || pending) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open, pending])

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        className="relative inline-flex min-h-9 items-center gap-1.5 rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-accent"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="size-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M13 2 3 14h9l-1 8 10-12h-9z" />
        </svg>
        Scenarios
        {(props.rainWarningActive || pending) && (
          <span
            aria-hidden="true"
            className="absolute -top-1 -right-1 size-2.5 rounded-full bg-status-warning"
          />
        )}
      </button>
      <div
        id={menuId}
        role="group"
        aria-label="Scenarios menu"
        hidden={!open}
        className="fixed inset-x-3 z-50 mt-2 max-h-[60dvh] overflow-y-auto overscroll-contain rounded-lg border border-line bg-surface shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:max-h-[70dvh] sm:w-80"
      >
        <SimulationEventsPanel {...props} onPendingChange={onPendingChange} />
      </div>
    </div>
  )
}
