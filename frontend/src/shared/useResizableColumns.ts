// Anchos de columna arrastrables "estilo Excel" (2026-08-09, a petición de Julio: "modificar la
// anchura de las columnas... y que sea posible... directamente como en excel"), persistidos en
// `localStorage` por tabla (mismo navegador) para que el ajuste sobreviva a recargar la página,
// igual que Excel recuerda el ancho de columna de un fichero.
import { useCallback, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'

type Widths = Record<string, number>

function readStored(storageKey: string, defaults: Widths): Widths {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return defaults
    return { ...defaults, ...(JSON.parse(raw) as Widths) }
  } catch {
    return defaults
  }
}

const MIN_WIDTH = 32

export function useResizableColumns(storageKey: string, defaults: Widths) {
  const [widths, setWidths] = useState<Widths>(() => readStored(storageKey, defaults))
  const widthsRef = useRef(widths)
  widthsRef.current = widths

  const startResize = useCallback(
    (key: string) => (e: ReactMouseEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const startWidth = widthsRef.current[key] ?? defaults[key] ?? 100

      const onMouseMove = (moveEvent: MouseEvent) => {
        const next = Math.max(MIN_WIDTH, startWidth + (moveEvent.clientX - startX))
        setWidths((w) => ({ ...w, [key]: next }))
      }
      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('mouseup', onMouseUp)
        try {
          localStorage.setItem(storageKey, JSON.stringify(widthsRef.current))
        } catch {
          // localStorage puede fallar (modo privado, cuota): el ancho sigue funcionando en
          // memoria durante esta sesión, solo no sobrevive a recargar.
        }
      }
      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    },
    [defaults, storageKey],
  )

  return { widths, startResize }
}
