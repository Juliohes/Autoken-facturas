// Tasas de IVA cerradas para el desplegable de tramos (spec S6.1 C9/C10): solo hay 4 posibles en
// España para este dominio (21/10/4 y exento). Nunca un valor libre al añadir/editar desde aquí.
import type { TaxLineForm } from './formState'

export const TAX_RATES = ['21', '10', '4', '0'] as const
export type TaxRate = (typeof TAX_RATES)[number]

/** Etiqueta legible de una tasa: "21%" o, para el 0%, "Sin IVA" (más claro que "0%"). */
export function taxRateLabel(rate: string): string {
  return rate === '0' ? 'Sin IVA' : `${rate}%`
}

/** Tasas de la lista cerrada que TODAVÍA no tienen un tramo en el formulario (spec C9/C10). */
export function availableTaxRates(lines: Pick<TaxLineForm, 'iva_pct'>[]): TaxRate[] {
  const used = new Set(lines.map((line) => line.iva_pct))
  return TAX_RATES.filter((rate) => !used.has(rate))
}
