// Cabecera de columna de una tabla TanStack: ordena al pulsar (si la columna lo permite) y se
// redimensiona arrastrando el borde derecho, con ratón O CON EL DEDO (2026-08-10) -- el mismo
// `header.getResizeHandler()` sirve para `onMouseDown` y `onTouchStart`, la propia librería decide
// según el evento real; no hay dos caminos de código separados que mantener en sincronía como con
// el hook casero anterior.
//
// Asa ensanchada (10px) con fondo tenue permanente, no solo al pasar el ratón (hallazgo de Julio:
// costaba encontrarla/agarrarla).
import { flexRender, type Header } from '@tanstack/react-table'

interface Props<TData> {
  header: Header<TData, unknown>
  /** Para el `aria-label` del asa: `header.column.columnDef.header` puede ser una función de
   * render, no siempre texto plano, así que el nombre legible se pasa aparte. */
  label: string
}

export function DataTableTh<TData>({ header, label }: Props<TData>) {
  const canSort = header.column.getCanSort()
  const canResize = header.column.getCanResize()
  const sorted = header.column.getIsSorted()

  return (
    <th
      className="relative p-2 pr-4"
      style={{ width: header.getSize() }}
      aria-sort={
        canSort ? (sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none') : undefined
      }
    >
      {header.isPlaceholder ? null : canSort ? (
        <button
          type="button"
          onClick={header.column.getToggleSortingHandler()}
          className="flex w-full items-center gap-1 truncate text-left hover:text-emerald-400"
        >
          <span className="truncate">
            {flexRender(header.column.columnDef.header, header.getContext())}
          </span>
          <span aria-hidden="true" className="text-xs leading-none">
            {sorted === 'asc' ? '▲' : sorted === 'desc' ? '▼' : ''}
          </span>
        </button>
      ) : (
        <span className="block truncate">
          {flexRender(header.column.columnDef.header, header.getContext())}
        </span>
      )}
      {canResize && (
        <span
          role="separator"
          aria-orientation="vertical"
          aria-label={`Redimensionar columna ${label}`}
          onMouseDown={header.getResizeHandler()}
          onTouchStart={header.getResizeHandler()}
          className="absolute right-0 top-0 h-full w-2.5 touch-none cursor-col-resize select-none rounded-sm bg-slate-500/20 hover:bg-emerald-500/60 active:bg-emerald-500/80"
        />
      )}
    </th>
  )
}
