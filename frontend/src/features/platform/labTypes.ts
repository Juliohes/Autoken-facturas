// Tipos de dominio del laboratorio OCR (S6.2).
//
// `GET .../invoices/{file_id}/lab` responde `dict[str, object]` en el backend (mismo criterio que
// `GET /uploads/{id}/review`, S2.4): el OpenAPI lo expone como objeto libre, así que se declara el
// contrato real aquí para consumirlo tipado. `GET .../invoices` sí responde un modelo Pydantic
// (`InvoiceRowOut`), así que `LabInvoiceRow` deriva del esquema generado en vez de duplicar sus
// campos a mano (mismo patrón que `features/panel/types.ts::InvoiceRow`, hallazgo de auditoría).
import type { components } from '../../api/schema'
import type { ReviewResponse } from '../confirmation/types'

export type LabInvoiceRow = components['schemas']['LabInvoiceRowOut']

/** Lectura 1 (IA cruda, spec C6/C7): la respuesta del proveedor tal cual + qué motor la produjo. */
export interface Reading1 {
  raw: Record<string, unknown>
  engine: string
  model: string
}

/** Lectura 2 (tras ajustes internos, spec C8/C9): mismo shape que `GET /uploads/{id}/review`
 * (S2.4) — reutilizado tal cual, no reinventado (la spec C8 lo exige explícitamente). */
export type Reading2 = ReviewResponse

/** Fila de la tabla unificada (S6.6 Área B/C): columna 2 ("decidió el sistema", reconstruida desde
 * `ocr_corrections` o, si no hay fila, desde la Lectura 1 — nunca desde la columna 3) vs columna 3
 * ("confirmado humano"). `match=null` cuando la columna 3 es `null` (campo no comparable, C8):
 * badge neutro, nunca rojo ni verde. */
export interface FieldComparison {
  field: string
  column_2: string | null
  column_3: string | null
  match: boolean | null
}

export interface TaxLineDict {
  iva_pct: string
  base: string
  cuota: string
}

/** Tramos de IVA (S6.6 C9): fila manual, no encaja en el bucle de campos escalares — un badge que
 * compara el conjunto completo (rojo si cualquier tramo difiere o si el número de tramos difiere). */
export interface TaxLinesComparison {
  column_2: TaxLineDict[]
  column_3: TaxLineDict[]
  match: boolean
}

/** Lectura 3 (guardado final, spec S6.6 C10/C11): la factura confirmada + la tabla unificada
 * campo a campo (sustituye a la vieja lista de correcciones de S6.2, que solo listaba diferencias). */
export interface Reading3 {
  invoice: Record<string, unknown>
  field_comparison: FieldComparison[]
  tax_lines_comparison: TaxLinesComparison
}

export interface RankingEntry {
  engine: string
  model: string
  reading: Record<string, unknown>
  score: number
}

/** Respuesta completa de `GET .../invoices/{file_id}/lab` (spec §3, área B-E). */
export interface LabDetail {
  reading_1: Reading1 | null
  reading_2: Reading2 | null
  reading_3: Reading3
  ranking: RankingEntry[]
  ranking_available: boolean
}
