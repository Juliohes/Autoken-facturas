// Tipos de dominio del laboratorio OCR (S6.2).
//
// `GET .../invoices/{file_id}/lab` responde `dict[str, object]` en el backend (mismo criterio que
// `GET /uploads/{id}/review`, S2.4): el OpenAPI lo expone como objeto libre, así que se declara el
// contrato real aquí para consumirlo tipado. `GET .../invoices` sí responde un modelo Pydantic
// (`InvoiceRowOut`), así que `LabInvoiceRow` deriva del esquema generado en vez de duplicar sus
// campos a mano (mismo patrón que `features/panel/types.ts::InvoiceRow`, hallazgo de auditoría).
import type { components } from '../../api/schema'
import type { ReviewResponse } from '../confirmation/types'

export type LabInvoiceRow = components['schemas']['platform_admin__lab_router__InvoiceRowOut']

/** Lectura 1 (IA cruda, spec C6/C7): la respuesta del proveedor tal cual + qué motor la produjo. */
export interface Reading1 {
  raw: Record<string, unknown>
  engine: string
  model: string
}

/** Lectura 2 (tras ajustes internos, spec C8/C9): mismo shape que `GET /uploads/{id}/review`
 * (S2.4) — reutilizado tal cual, no reinventado (la spec C8 lo exige explícitamente). */
export type Reading2 = ReviewResponse

export interface Reading3Correction {
  field: string
  ai_value: string | null
  human_value: string | null
}

/** Lectura 3 (guardado final, spec C10/C11): la factura confirmada + el diff de correcciones. */
export interface Reading3 {
  invoice: Record<string, unknown>
  corrections: Reading3Correction[]
  has_corrections: boolean
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
