// Lógica pura del veredicto del CIF de contraparte (spec §2, C3): traduce el
// `counterparty_verdict` a un tono + mensaje. Separada de la presentación
// (CounterpartyVerdictBlock) para poder probarla sin renderizar.
import type { CounterpartyVerdict } from './types'

export type VerdictTone = 'ok' | 'warn' | 'error'

export interface RenderedVerdict {
  tone: VerdictTone
  message: string
}

export function renderVerdict(verdict: CounterpartyVerdict): RenderedVerdict {
  switch (verdict.status) {
    case 'valid':
      // valid + nombre que casa -> verde; valid + nombre que no casa -> aviso con
      // la razón social oficial (C3).
      if (verdict.name_match === false) {
        const official = verdict.official_name ?? 'la registrada oficialmente'
        return {
          tone: 'warn',
          message: `El nombre no coincide con la razón social oficial: ${official}`,
        }
      }
      return { tone: 'ok', message: 'CIF de contraparte verificado' }
    case 'invalid':
      return { tone: 'error', message: 'CIF de contraparte inválido' }
    case 'not_found':
      return { tone: 'error', message: 'CIF de contraparte no encontrado' }
    case 'unverified':
      return { tone: 'warn', message: 'No se pudo verificar el CIF: revisar manual' }
  }
}
