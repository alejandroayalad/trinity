import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Keep keyboard focus inside a container while it is open (dialog, drawer).
 *
 * On open: remember the focused element and move focus into the container.
 * While open: Tab on the last element goes to the first; Shift+Tab on the
 * first goes to the last; Escape calls onEscape.
 * On close: return focus to the remembered element, for example "☰ Menu".
 *
 * onEscape is kept in a ref. A parent that passes a new function on each
 * render therefore does not restart the trap or move focus again.
 */
export function useFocusTrap(containerRef: RefObject<HTMLElement | null>, active: boolean, onEscape: () => void): void {
  const escape = useRef(onEscape)
  useEffect(() => {
    escape.current = onEscape
  }, [onEscape])

  useEffect(() => {
    const container = containerRef.current
    if (!active || container === null) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null

    const focusables = () => Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE))
    // Focus the first control, or the container itself when it has none.
    ;(focusables()[0] ?? container).focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        escape.current()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusables()
      if (items.length === 0) {
        event.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      opener?.focus()
    }
  }, [active, containerRef])
}
