// Banner / Toast de aviso (Bloque 2). Tonos info/ok/warn/bad; el de error usa role="alert".
import type { ReactNode } from 'react'

export type BannerTone = 'info' | 'ok' | 'warn' | 'bad'

export interface BannerProps {
  /** Tono del aviso. */
  tone?: BannerTone
  /** Contenido del aviso. */
  children: ReactNode
  /** Acción opcional (botón/enlace) al final del aviso. */
  action?: ReactNode
}

const TONE_CLASS: Record<BannerTone, string> = {
  info: 'tn-banner-info',
  ok: 'tn-banner-ok',
  warn: 'tn-banner-warn',
  bad: 'tn-banner-bad',
}

/** Aviso accesible; el tono "bad" se anuncia de forma asertiva (role=alert). */
export function Banner({ tone = 'info', children, action }: BannerProps) {
  return (
    <div role={tone === 'bad' ? 'alert' : 'status'} className={`tn-banner ${TONE_CLASS[tone]}`}>
      <div className="tn-banner-body">{children}</div>
      {action}
    </div>
  )
}
