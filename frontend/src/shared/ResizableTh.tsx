// Cabecera de columna con asa de arrastre para redimensionar (2026-08-09), pareja de
// `useResizableColumns`. Presentación pura: no sabe de dónde viene el ancho ni dónde se guarda.
//
// Ordenar al pulsar la cabecera (2026-08-10, `useColumnSort`) es opcional: sin `onSortClick` la
// etiqueta es texto plano, como antes. Asa de arrastre ensanchada (6px -> 10px) y con un fondo
// tenue permanente, no solo al pasar el ratón (hallazgo de Julio: costaba encontrarla/agarrarla).
//
// `onResizeTouchStart` (2026-08-10, hallazgo real reproducido con un dispositivo táctil: el asa
// solo escuchaba el ratón, así que en un móvil/tablet el arrastre no hacía nada) — `touch-none`
// evita que el gesto también haga scroll de la página mientras se arrastra.
import type { SortDirection } from './useColumnSort'

interface Props {
  label: string
  width: number
  onResizeStart: (e: React.MouseEvent) => void
  onResizeTouchStart: (e: React.TouchEvent) => void
  sortDirection?: SortDirection | null
  onSortClick?: () => void
}

export function ResizableTh({
  label,
  width,
  onResizeStart,
  onResizeTouchStart,
  sortDirection,
  onSortClick,
}: Props) {
  return (
    <th
      className="relative p-2 pr-4"
      style={{ width }}
      aria-sort={
        onSortClick
          ? sortDirection === 'asc'
            ? 'ascending'
            : sortDirection === 'desc'
              ? 'descending'
              : 'none'
          : undefined
      }
    >
      {onSortClick ? (
        <button
          type="button"
          onClick={onSortClick}
          className="flex w-full items-center gap-1 truncate text-left hover:text-emerald-400"
        >
          <span className="truncate">{label}</span>
          <span aria-hidden="true" className="text-xs leading-none">
            {sortDirection === 'asc' ? '▲' : sortDirection === 'desc' ? '▼' : ''}
          </span>
        </button>
      ) : (
        <span className="block truncate">{label}</span>
      )}
      <span
        role="separator"
        aria-orientation="vertical"
        aria-label={`Redimensionar columna ${label}`}
        onMouseDown={onResizeStart}
        onTouchStart={onResizeTouchStart}
        className="absolute right-0 top-0 h-full w-2.5 touch-none cursor-col-resize select-none rounded-sm bg-slate-500/20 hover:bg-emerald-500/60 active:bg-emerald-500/80"
      />
    </th>
  )
}
