// Field (Bloque 2): label + control + hint + error accesible. El error se enlaza con
// aria-describedby al control y se anuncia con role="alert".
import { useId, type ReactNode } from 'react'

export interface FieldProps {
  /** Etiqueta visible del campo. */
  label: string
  /** Control (input/select/textarea) ya construido por el llamante. */
  children: ReactNode
  /** Texto de ayuda opcional. */
  hint?: string
  /** Mensaje de error opcional (se anuncia). */
  error?: string
  /** id del control para asociar el label; si no se pasa, se genera uno. */
  htmlFor?: string
}

/** Campo de formulario accesible. */
export function Field({ label, children, hint, error, htmlFor }: FieldProps) {
  const autoId = useId()
  const controlId = htmlFor ?? autoId
  const hintId = hint ? `${controlId}-hint` : undefined
  const errorId = error ? `${controlId}-error` : undefined
  return (
    <div className="tn-field">
      <label htmlFor={controlId} className="tn-field-label">{label}</label>
      {children}
      {hint && <p id={hintId} className="tn-field-hint">{hint}</p>}
      {error && <p id={errorId} role="alert" className="tn-field-error">{error}</p>}
    </div>
  )
}
