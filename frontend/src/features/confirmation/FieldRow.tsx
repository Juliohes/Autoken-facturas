// Fila de un campo editable con su marca de confianza (spec §2, C2). Presentación
// pura: recibe el valor y la confianza, no conoce la lógica de negocio.
import type { ChangeEvent, ReactNode } from 'react'

import { confidenceLabel, confidenceMark } from './confidence'
import type { Confidence } from './types'

interface FieldRowProps {
  name: string
  label: string
  value: string
  confidence?: Confidence
  /** Sin confianza que puntuar (identidad propia conocida, ADR-0011). */
  scored?: boolean
  type?: 'text' | 'date'
  onChange: (value: string) => void
  /** Aviso adicional junto a la etiqueta, además de la marca de confianza (p. ej. el check verde
   * de CIF verificado, 2026-08-08): mismo sitio, no conoce de dónde viene. */
  extraBadge?: ReactNode
}

// Clases de color por marca (amarillo = dudoso; rojo = revisar/no leído; sin marca = alta).
const MARK_CLASS: Record<string, string> = {
  ok: 'border-slate-600',
  dudoso: 'border-yellow-500 bg-yellow-500/10',
  revisar: 'border-red-500 bg-red-500/10',
  no_leido: 'border-red-500 bg-red-500/10',
}

export function FieldRow({
  name,
  label,
  value,
  confidence,
  scored = true,
  type = 'text',
  onChange,
  extraBadge,
}: FieldRowProps) {
  const mark = scored ? confidenceMark(confidence, value.trim() !== '') : 'ok'
  const markText = confidenceLabel(mark)

  return (
    <label className="flex flex-col gap-1" data-testid={`field-${name}`}>
      <span className="flex items-center gap-2 text-sm text-slate-300">
        {label}
        {markText && (
          <span
            data-testid={`mark-${name}`}
            data-mark={mark}
            className={
              mark === 'dudoso'
                ? 'rounded px-1.5 py-0.5 text-xs font-semibold text-yellow-300'
                : 'rounded px-1.5 py-0.5 text-xs font-semibold text-red-300'
            }
          >
            {markText}
          </span>
        )}
        {extraBadge}
      </span>
      <input
        type={type}
        name={name}
        aria-label={label}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        className={`rounded-md border bg-slate-800 px-3 py-2 text-slate-100 ${MARK_CLASS[mark]}`}
      />
    </label>
  )
}
