// Cabecera de columna con asa de arrastre para redimensionar (2026-08-09), pareja de
// `useResizableColumns`. Presentación pura: no sabe de dónde viene el ancho ni dónde se guarda.
interface Props {
  label: string
  width: number
  onResizeStart: (e: React.MouseEvent) => void
}

export function ResizableTh({ label, width, onResizeStart }: Props) {
  return (
    <th className="relative p-2 pr-3" style={{ width }}>
      <span className="block truncate">{label}</span>
      <span
        role="separator"
        aria-orientation="vertical"
        aria-label={`Redimensionar columna ${label}`}
        onMouseDown={onResizeStart}
        className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize select-none hover:bg-emerald-500/50"
      />
    </th>
  )
}
