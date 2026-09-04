// SegmentedControl (Bloque 2): selector de opciones mutuamente excluyentes (p. ej. Recibida/
// Emitida). Accesible como radiogroup; el estado activo usa acento naranja con texto navy (AA).
export interface SegmentedOption<T extends string> {
  /** Valor de la opción. */
  value: T
  /** Texto visible. */
  label: string
}

export interface SegmentedControlProps<T extends string> {
  /** Nombre accesible del grupo. */
  label: string
  /** Opciones a mostrar. */
  options: ReadonlyArray<SegmentedOption<T>>
  /** Valor seleccionado (o null si aún no se ha elegido). */
  value: T | null
  /** Callback al cambiar. */
  onChange: (value: T) => void
}

/** Selector segmentado accesible. */
export function SegmentedControl<T extends string>({ label, options, value, onChange }: SegmentedControlProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="tn-segmented">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={`tn-segmented-option${value === option.value ? ' tn-segmented-option-active' : ''}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
