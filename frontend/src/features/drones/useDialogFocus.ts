import { useEffect, type RefObject } from 'react'

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Modal focus handling: moves focus into the dialog when it opens (to the element marked
 * `data-autofocus`, else the dialog itself), keeps Tab inside it, and gives focus back to whatever
 * had it before when the dialog closes.
 */
export function useDialogFocus(dialog: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = dialog.current
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const target = root?.querySelector<HTMLElement>('[data-autofocus]') ?? root
    target?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !root) return
      const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (items.length === 0) {
        event.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (!root.contains(active) || (event.shiftKey && (active === first || active === root))) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      if (previous?.isConnected) previous.focus()
    }
  }, [dialog])
}
