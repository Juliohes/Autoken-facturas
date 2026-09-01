// Card / Section (Bloque 2): superficie con borde y sombra de tarjeta; Section añade título.
import type { ReactNode } from 'react'

export interface CardProps {
  /** Contenido de la tarjeta. */
  children: ReactNode
  /** Clases extra opcionales. */
  className?: string
}

/** Tarjeta de superficie clara. */
export function Card({ children, className = '' }: CardProps) {
  return <div className={`tn-card${className ? ` ${className}` : ''}`}>{children}</div>
}

export interface SectionProps {
  /** Título de la sección (versalitas). */
  title: string
  /** Contenido. */
  children: ReactNode
  /** Clases extra opcionales. */
  className?: string
}

/** Sección con título y cuerpo. */
export function Section({ title, children, className = '' }: SectionProps) {
  return (
    <section className={`tn-section${className ? ` ${className}` : ''}`}>
      <h2 className="tn-section-title">{title}</h2>
      <div className="tn-section-body">{children}</div>
    </section>
  )
}
