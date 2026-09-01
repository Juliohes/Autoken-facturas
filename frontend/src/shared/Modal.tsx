import { useEffect, useId, useRef, type ReactNode } from 'react'

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

interface Props {
  title: string
  onClose: () => void
  children: ReactNode
  panelClassName?: string
  headerAction?: ReactNode
  accessibleName?: string
  overlayClassName?: string
  hideTitle?: boolean
}

export function Modal({
  title,
  onClose,
  children,
  panelClassName = '',
  headerAction,
  accessibleName,
  overlayClassName = '',
  hideTitle = false,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const titleId = useId()
  onCloseRef.current = onClose

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const dialog = dialogRef.current
    const focusable = dialog?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    const firstControl = focusable?.[0]
    ;(firstControl ?? dialog)?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab' || !dialog) return

      const controls = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)]
      if (controls.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      previouslyFocused?.focus()
    }
  }, [])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={accessibleName ? undefined : titleId}
      aria-label={accessibleName}
      className={`fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 ${overlayClassName}`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current()
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={`tn-liquid-glass w-full p-4 outline-none ${panelClassName}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={headerAction ? 'mb-3 flex items-center justify-between gap-3' : undefined}>
          <h2 id={titleId} className={hideTitle ? 'sr-only' : 'text-lg font-semibold'}>
            {title}
          </h2>
          {headerAction}
        </div>
        {children}
      </div>
    </div>
  )
}
