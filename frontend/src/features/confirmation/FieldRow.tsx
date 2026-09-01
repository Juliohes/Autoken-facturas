// Fila de un campo editable. La confianza del OCR no se representa como error visual:
// la persona revisa los datos y lo confirma con la casilla global del formulario.
import type { ChangeEvent, ReactNode } from 'react'

interface FieldRowProps {
  name: string
  label: string
  value: string
  type?: 'text' | 'date'
  onChange: (value: string) => void
  /** Aviso adicional junto a la etiqueta, además de la marca de confianza (p. ej. el check verde
   * de CIF verificado, 2026-08-08): mismo sitio, no conoce de dónde viene. */
  extraBadge?: ReactNode
}

export function FieldRow({
  name,
  label,
  value,
  type = 'text',
  onChange,
  extraBadge,
}: FieldRowProps) {
  return (
    <label className="flex flex-col gap-1" data-testid={`field-${name}`}>
      <span className="flex items-center gap-2 text-sm text-muted">
        {label}
        {extraBadge}
      </span>
      <input
        type={type}
        name={name}
        aria-label={label}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        className="rounded-md border border-line bg-surface px-3 py-2 text-fg"
      />
    </label>
  )
}
