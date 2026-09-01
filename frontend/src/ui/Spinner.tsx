// Spinner accesible (Bloque 2). Anuncia el estado de carga a lectores de pantalla.
export interface SpinnerProps {
  /** Texto accesible del estado de carga. */
  label?: string
}

/** Indicador de carga. */
export function Spinner({ label = 'Cargando…' }: SpinnerProps) {
  return (
    <span role="status" aria-live="polite" className="tn-spinner-wrap">
      <span aria-hidden="true" className="tn-spinner" />
      <span className="sr-only">{label}</span>
    </span>
  )
}
