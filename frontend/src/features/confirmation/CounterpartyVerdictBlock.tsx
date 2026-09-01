// Bloque del veredicto del CIF de contraparte (spec §2, C3). Presentación pura a
// partir del `counterparty_verdict` de la revisión (ADR-0011). La lógica
// tono/mensaje vive en `verdict.ts`. Estilo por tokens semánticos (Bloque 6): mismos
// data-testid/data-tone/data-status que ya verifican los tests, solo cambia el color.
import { Banner, type BannerTone } from '../../ui'
import type { CounterpartyVerdict } from './types'
import { renderVerdict, type VerdictTone } from './verdict'

interface Props {
  verdict: CounterpartyVerdict
}

const TONE_TO_BANNER: Record<VerdictTone, BannerTone> = {
  ok: 'ok',
  warn: 'warn',
  error: 'bad',
}

export function CounterpartyVerdictBlock({ verdict }: Props) {
  const { tone, message } = renderVerdict(verdict)
  return (
    <div data-testid="counterparty-verdict" data-status={verdict.status} data-tone={tone}>
      <Banner tone={TONE_TO_BANNER[tone]}>{message}</Banner>
    </div>
  )
}
