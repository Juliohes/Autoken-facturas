// Campo de contraseña con mostrar/ocultar (extraído de LoginScreen, Bloque 4 de
// PROMPT-AUTOFACTU-AUTH-COMPLETO): el mismo control se repite ahora en login, registro,
// restablecimiento y activación. El valor nunca cambia al alternar visibilidad, solo el `type`.
import { useId, useState, type ChangeEvent } from 'react'

export interface PasswordFieldProps {
  /** Etiqueta visible del campo. */
  label: string
  value: string
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  /** id del input; si no se pasa, se genera uno (para asociar aria-controls). */
  id?: string
  required?: boolean
  autoComplete?: string
}

/** Campo de contraseña accesible con alternador de visibilidad (mismo patrón que LoginScreen). */
export function PasswordField({
  label,
  value,
  onChange,
  id,
  required,
  autoComplete,
}: PasswordFieldProps) {
  const autoId = useId()
  const controlId = id ?? autoId
  const [visible, setVisible] = useState(false)

  return (
    <label className="tn-login-label flex flex-col text-sm">
      {label}
      <span className="tn-password-field">
        <input
          id={controlId}
          type={visible ? 'text' : 'password'}
          required={required}
          autoComplete={autoComplete}
          value={value}
          onChange={onChange}
          className="tn-login-input rounded px-2 py-1"
        />
        <button
          type="button"
          aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
          aria-controls={controlId}
          aria-pressed={visible}
          className="tn-password-toggle"
          onClick={() => setVisible((v) => !v)}
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
          >
            {visible ? (
              <>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A10.8 10.8 0 0 1 12 5c5 0 8.6 4.2 9.8 7a12.8 12.8 0 0 1-3 4.4M6.2 6.2A13.2 13.2 0 0 0 2.2 12c1.2 2.8 4.8 7 9.8 7 1 0 2-.2 2.9-.5"
                />
              </>
            ) : (
              <>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M2.2 12C3.4 9.2 7 5 12 5s8.6 4.2 9.8 7c-1.2 2.8-4.8 7-9.8 7s-8.6-4.2-9.8-7Z"
                />
                <circle cx="12" cy="12" r="2.5" />
              </>
            )}
          </svg>
        </button>
      </span>
    </label>
  )
}
