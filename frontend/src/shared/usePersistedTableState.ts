// Estado de una tabla "estilo Excel" (anchos de columna + orden), sobre TanStack Table
// (2026-08-10). Sustituye a los hooks caseros `useColumnSort`/`useResizableColumns` (2026-08-09/10):
// aquellos solo sabían escuchar al ratón -- el redimensionado tuvo que parchearse a mano para
// soportar el dedo (`useResizableColumns.startResizeTouch`) y aun así seguía sintiéndose frágil
// (asa de pocos píxeles, sin la ergonomía real de una hoja de cálculo). TanStack Table resuelve el
// redimensionado con el mismo `header.getResizeHandler()` para ratón Y táctil (una única función,
// mantenida por la librería, no por nosotros) y trae el ordenado ya integrado.
//
// El ancho de columna se recuerda entre sesiones (mismo criterio que antes, `localStorage` por
// tabla); el orden NO se recuerda (vuelve siempre al orden de llegada al recargar), igual que el
// hook casero anterior.
//
// `columnSizing`/`columnSizingInfo` viven en UN SOLO `useState` (no dos aparte), a propósito
// (hallazgo real, reproducido con un test): el asa de arrastre de TanStack calcula el nuevo ancho
// con un efecto colateral entre dos actualizaciones seguidas -- la primera (`columnSizingInfo`)
// calcula el delta y dej deja el resultado en una variable compartida; la segunda
// (`columnSizing`) lo lee. Si cada una vive en su propio `useState`, React no garantiza que las
// procese en el mismo orden en que se llamaron (curioso pero real: se vio fallar SOLO cuando el
// panel se montaba una segunda vez en la misma sesión de test, nunca en aislado) -- el arrastre se
// quedaba sin efecto en ese caso. Un único estado fuerza a React a aplicar ambas actualizaciones en
// el orden exacto en que se despacharon.
import { useState } from 'react'
import type {
  ColumnSizingInfoState,
  ColumnSizingState,
  OnChangeFn,
  SortingState,
} from '@tanstack/react-table'

function readStoredWidths(storageKey: string): ColumnSizingState {
  try {
    const raw = localStorage.getItem(storageKey)
    return raw ? (JSON.parse(raw) as ColumnSizingState) : {}
  } catch {
    return {}
  }
}

const DEFAULT_SIZING_INFO: ColumnSizingInfoState = {
  startOffset: null,
  startSize: null,
  deltaOffset: null,
  deltaPercentage: null,
  isResizingColumn: false,
  columnSizingStart: [],
}

interface State {
  columnSizing: ColumnSizingState
  columnSizingInfo: ColumnSizingInfoState
  sorting: SortingState
}

export function usePersistedTableState(storageKey: string) {
  const [state, setState] = useState<State>(() => ({
    columnSizing: readStoredWidths(storageKey),
    columnSizingInfo: DEFAULT_SIZING_INFO,
    sorting: [],
  }))

  const onColumnSizingChange: OnChangeFn<ColumnSizingState> = (updater) => {
    setState((prev) => {
      const columnSizing = typeof updater === 'function' ? updater(prev.columnSizing) : updater
      try {
        localStorage.setItem(storageKey, JSON.stringify(columnSizing))
      } catch {
        // localStorage puede fallar (modo privado, cuota): el ancho sigue funcionando en memoria
        // durante esta sesión, solo no sobrevive a recargar.
      }
      return { ...prev, columnSizing }
    })
  }

  const onColumnSizingInfoChange: OnChangeFn<ColumnSizingInfoState> = (updater) => {
    setState((prev) => ({
      ...prev,
      columnSizingInfo: typeof updater === 'function' ? updater(prev.columnSizingInfo) : updater,
    }))
  }

  const setSorting: OnChangeFn<SortingState> = (updater) => {
    setState((prev) => ({
      ...prev,
      sorting: typeof updater === 'function' ? updater(prev.sorting) : updater,
    }))
  }

  return {
    columnSizing: state.columnSizing,
    onColumnSizingChange,
    columnSizingInfo: state.columnSizingInfo,
    onColumnSizingInfoChange,
    sorting: state.sorting,
    setSorting,
  }
}
