// Botón del sistema de diseño (Bloque 2). Variantes y tamaños por tokens; el primario usa el
// acento naranja con texto navy (AA). Soporta loading, disabled e iconos laterales (lucide).
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Variante visual/semántica. */
  variant?: ButtonVariant
  /** Tamaño (alto táctil mínimo garantizado). */
  size?: ButtonSize
  /** Muestra spinner y bloquea la acción mientras sea true. */
  loading?: boolean
  /** Icono a la izquierda del contenido (decorativo, aria-hidden). */
  iconLeft?: ReactNode
  /** Icono a la derecha del contenido (decorativo, aria-hidden). */
  iconRight?: ReactNode
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'tn-btn-primary',
  secondary: 'tn-btn-secondary',
  ghost: 'tn-btn-ghost',
  danger: 'tn-btn-danger',
}

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: 'tn-btn-sm',
  md: 'tn-btn-md',
  lg: 'tn-btn-lg',
}

/** Botón accesible del sistema de diseño. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, iconLeft, iconRight, className = '', children, disabled, ...rest },
  ref,
) {
  const isDisabled = disabled || loading
  return (
    <button
      ref={ref}
      type="button"
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={`tn-btn ${VARIANT_CLASS[variant]} ${SIZE_CLASS[size]}${className ? ` ${className}` : ''}`}
      {...rest}
    >
      {loading && <span aria-hidden="true" className="tn-btn-spinner" />}
      {!loading && iconLeft}
      <span className="tn-btn-content">{children}</span>
      {!loading && iconRight}
    </button>
  )
})
