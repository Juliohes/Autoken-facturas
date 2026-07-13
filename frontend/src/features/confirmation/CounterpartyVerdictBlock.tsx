// Bloque del veredicto del CIF de contraparte (spec §2, C3). Presentación pura a
// partir del `counterparty_verdict` de la revisión (ADR-0011). La lógica
// tono/mensaje vive en `verdict.ts`.
import type { CounterpartyVerdict } from './types'
import { renderVerdict, type VerdictTone } from './verdict'

interface Props {
  verdict: CounterpartyVerdict
}

const TONE_CLASS: Record<VerdictTone, string> = {
  ok: 'border-emerald-500 bg-emerald-500/10 text-emerald-200',
  warn: 'border-yellow-500 bg-yellow-500/10 text-yellow-200',
  error: 'border-red-500 bg-red-500/10 text-red-200',
}

export function CounterpartyVerdictBlock({ verdict }: Props) {
  const { tone, message } = renderVerdict(verdict)
  return (
    <div
      data-testid="counterparty-verdict"
      data-status={verdict.status}
      data-tone={tone}
      className={`rounded-md border px-3 py-2 text-sm ${TONE_CLASS[tone]}`}
    >
      {message}
    </div>
  )
}
