// StatusBadge — única fuente de verdad estado→{color, icono, texto} (Bloque 2).
// Regla AA: el estado NUNCA se comunica solo por color; siempre color + icono + texto.
import { AlertCircle, AlertTriangle, CheckCircle2, Clock, XCircle, type LucideIcon } from 'lucide-react'

export type StatusTone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

export interface StatusBadgeProps {
  /** Tono semántico del estado. */
  tone: StatusTone
  /** Texto visible del estado. */
  label: string
  /** Icono opcional; si no se pasa, se elige por el tono. */
  icon?: LucideIcon
}

const DEFAULT_ICON: Record<StatusTone, LucideIcon> = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  bad: XCircle,
  neutral: Clock,
  info: AlertCircle,
}

const TONE_CLASS: Record<StatusTone, string> = {
  ok: 'tn-status-ok',
  warn: 'tn-status-warn',
  bad: 'tn-status-bad',
  neutral: 'tn-status-neutral',
  info: 'tn-status-info',
}

/** Insignia de estado accesible: color + icono + texto. */
export function StatusBadge({ tone, label, icon }: StatusBadgeProps) {
  const Icon = icon ?? DEFAULT_ICON[tone]
  return (
    <span className={`tn-status-badge ${TONE_CLASS[tone]}`} data-tone={tone}>
      <Icon aria-hidden="true" size={14} strokeWidth={2.2} className="tn-status-icon" />
      <span>{label}</span>
    </span>
  )
}
