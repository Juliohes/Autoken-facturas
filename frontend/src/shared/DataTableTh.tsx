// Cabecera de columna de una tabla TanStack: ordena al pulsar (si la columna lo permite) y se
// redimensiona arrastrando el borde derecho, con ratón O CON EL DEDO -- el mismo
// `header.getResizeHandler()` sirve para `onMouseDown` y `onTouchStart` (NO se añade también
// `onPointerDown`: muchos navegadores disparan `pointerdown` Y `mousedown` para el mismo gesto de
// ratón, así que escuchar los dos duplicaría el arrastre -- misma familia de fallo que ya costó
// diagnosticar en `usePersistedTableState.ts`).
//
// Asa MUY ensanchada (16px, antes 10px) y con contraste alto siempre visible -- no solo al pasar
// el ratón -- tras varios reportes seguidos de Julio de que seguía sin encontrarla/agarrarla en su
// PC pese a los arreglos anteriores del mecanismo en sí (verificado por separado con automatización
// de navegador real, ratón y dedo). Ante la duda de si el problema es el mecanismo o lo difícil que
// es dar con el sitio exacto, se prioriza lo segundo: un blanco mucho más grande y obvio no puede
// empeorar nada, y sí que arregla un problema real de precisión si era ese.
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
  const resizeHandler = header.getResizeHandler()

  return (
    <th
      className="relative p-2 pr-5"
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
          onMouseDown={resizeHandler}
          onTouchStart={resizeHandler}
          className="group absolute right-0 top-0 z-10 flex h-full w-4 touch-none cursor-col-resize select-none items-stretch justify-center"
        >
          <span className="w-1 rounded-full bg-slate-400 transition-colors group-hover:bg-emerald-400 group-active:bg-emerald-300" />
        </span>
      )}
    </th>
  )
}
