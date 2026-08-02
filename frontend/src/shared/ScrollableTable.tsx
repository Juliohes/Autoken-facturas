import { useEffect, useRef, useState, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

/**
 * Envoltorio para tablas anchas: además de la barra de scroll horizontal nativa (que en una tabla
 * con muchas filas queda fuera de la vista hasta bajar del todo), duplica esa misma barra ARRIBA
 * del contenido, sincronizada con la de abajo — a petición de Julio (2026-08-01), "una barra móvil
 * a lo ancho, tanto arriba como abajo".
 */
export function ScrollableTable({ children }: Props) {
  const topRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [contentWidth, setContentWidth] = useState(0)
  const isSyncing = useRef(false)

  // Sin dependencias: se remide en cada render (p. ej. cuando llegan filas nuevas de la API), sin
  // necesitar `ResizeObserver` (no disponible en el entorno de test). El `resize` de ventana cubre
  // además un cambio de ancho de viewport sin que el propio contenido cambie.
  useEffect(() => {
    const measure = () => {
      const width = contentRef.current?.scrollWidth ?? 0
      setContentWidth((prev) => (prev === width ? prev : width))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  })

  const syncFrom = (source: 'top' | 'bottom') => {
    if (isSyncing.current) {
      isSyncing.current = false
      return
    }
    const from = source === 'top' ? topRef.current : bottomRef.current
    const to = source === 'top' ? bottomRef.current : topRef.current
    if (!from || !to) return
    isSyncing.current = true
    to.scrollLeft = from.scrollLeft
  }

  return (
    <div>
      <div
        ref={topRef}
        className="overflow-x-auto overflow-y-hidden"
        onScroll={() => syncFrom('top')}
        aria-hidden="true"
        data-testid="scrollable-table-top-bar"
      >
        <div style={{ width: contentWidth, height: 1 }} />
      </div>
      <div
        ref={bottomRef}
        className="overflow-x-auto"
        onScroll={() => syncFrom('bottom')}
        data-testid="scrollable-table-bottom-bar"
      >
        <div ref={contentRef}>{children}</div>
      </div>
    </div>
  )
}
