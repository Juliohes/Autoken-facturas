// EmptyState (Bloque 2): estado vacío con icono, título, descripción y acción opcional.
import type { ReactNode } from 'react'

export interface EmptyStateProps {
  /** Icono decorativo (aria-hidden). */
  icon?: ReactNode
  /** Título del estado vacío. */
  title: string
  /** Descripción opcional. */
  description?: string
  /** Acción principal opcional (CTA). */
  action?: ReactNode
}

/** Estado vacío accesible y centrado. */
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="tn-empty-state">
      {icon && <div aria-hidden="true" className="tn-empty-icon">{icon}</div>}
      <p className="tn-empty-title">{title}</p>
      {description && <p className="tn-empty-desc">{description}</p>}
      {action && <div className="tn-empty-action">{action}</div>}
    </div>
  )
}
