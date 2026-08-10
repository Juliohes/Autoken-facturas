// Anchos de columna arrastrables "estilo Excel" (2026-08-09, a petición de Julio: "modificar la
// anchura de las columnas... y que sea posible... directamente como en excel"), persistidos en
// `localStorage` por tabla (mismo navegador) para que el ajuste sobreviva a recargar la página,
// igual que Excel recuerda el ancho de columna de un fichero.
//
// Soporte táctil (2026-08-10, hallazgo real: Julio no podía mover columnas "fácilmente"; reproducido
// con un dispositivo táctil emulado — el asa solo escuchaba `mousedown`/`mousemove`/`mouseup`, que un
// móvil/tablet no dispara al arrastrar con el dedo, así que el arrastre no hacía NADA ahí, sin importar
// lo grande que fuera el asa). `startResizeTouch` es la pareja de `startResize` para `touchstart`;
// ambas comparten el mismo estado y la misma persistencia.
import {
  useCallback,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type TouchEvent as ReactTouchEvent,
} from 'react'

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

  const persist = useCallback(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(widthsRef.current))
    } catch {
      // localStorage puede fallar (modo privado, cuota): el ancho sigue funcionando en memoria
      // durante esta sesión, solo no sobrevive a recargar.
    }
  }, [storageKey])

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
        persist()
      }
      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    },
    [defaults, persist],
  )

  const startResizeTouch = useCallback(
    (key: string) => (e: ReactTouchEvent) => {
      const touch = e.touches[0]
      if (!touch) return
      const startX = touch.clientX
      const startWidth = widthsRef.current[key] ?? defaults[key] ?? 100

      const onTouchMove = (moveEvent: TouchEvent) => {
        const t = moveEvent.touches[0]
        if (!t) return
        // Sin esto, el gesto también haría scroll de la página mientras se arrastra la columna.
        moveEvent.preventDefault()
        const next = Math.max(MIN_WIDTH, startWidth + (t.clientX - startX))
        setWidths((w) => ({ ...w, [key]: next }))
      }
      const onTouchEnd = () => {
        document.removeEventListener('touchmove', onTouchMove)
        document.removeEventListener('touchend', onTouchEnd)
        persist()
      }
      document.addEventListener('touchmove', onTouchMove, { passive: false })
      document.addEventListener('touchend', onTouchEnd)
    },
    [defaults, persist],
  )

  return { widths, startResize, startResizeTouch }
}
