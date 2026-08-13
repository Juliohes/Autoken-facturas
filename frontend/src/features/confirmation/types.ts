// Tipos de dominio de la pantalla de confirmación (S2.4).
//
// El endpoint `GET /uploads/{id}/review` responde `dict[str, object]` en el
// backend, así que el OpenAPI lo expone como objeto libre. Aquí se declara el
// contrato real (spec §2) para consumirlo tipado en toda la feature; el punto de
// entrada (`useReview`) es el único que hace el cast desde la respuesta cruda.

import type { components } from '../../api/schema'

/** Confianza del OCR por campo: alta/media/baja o ausente (spec §2). */
export type Confidence = 'alta' | 'media' | 'baja' | null

/** Estado del veredicto del CIF de contraparte (ADR-0011). */
export type CounterpartyStatus = 'valid' | 'invalid' | 'not_found' | 'unverified'

/** Veredicto del CIF de contraparte devuelto por `review` (spec §2, C3). */
export interface CounterpartyVerdict {
  status: CounterpartyStatus
  name_match: boolean | null
  official_name: string | null
}

/** Un tramo de IVA tal cual lo devuelve la extracción del OCR (base/rate/cuota). */
export interface ReviewTaxLine {
  base?: number | string | null
  rate?: number | string | null
  cuota?: number | string | null
}

/** Campos leídos (o `null` si no se leyeron; nunca inventados, regla 4). */
export interface ReviewFields {
  issue_date: string | null
  total_amount: string | null
  net_amount: string | null
  tax_amount: string | null
  invoice_number: string | null
  counterparty_tax_id: string | null
  counterparty_name: string | null
  tax_lines: ReviewTaxLine[]
}

/** Identidad propia conocida (no se lee por OCR, no se puntúa; ADR-0011). */
export interface OwnIdentity {
  cif: string | null
  name: string | null
}

/** Respuesta completa de `GET /uploads/{id}/review` (spec §2). */
export interface ReviewResponse {
  fields: ReviewFields
  confidences: Record<string, Confidence>
  counterparty_verdict: CounterpartyVerdict
  own: OwnIdentity
  warnings: string[]
  blocking_reasons: string[]
}

/** Motivos de bloqueo que el servidor reimpone en `confirm` (spec §2). */
export const BLOCKING_REASONS = {
  cifInvalid: 'counterparty_cif_invalid',
  cifNotFound: 'counterparty_cif_not_found',
  ownTaxIdMissing: 'own_tax_id_missing',
} as const

/** Aviso de descuadre aritmético (no bloquea; regla 5, C10). */
export const WARNING_IMBALANCE = 'descuadre'

/** Cuerpo tipado de `POST /uploads/{id}/confirm` (reutiliza el schema generado). */
export type ConfirmBody = components['schemas']['ConfirmIn'] & {
  /** S6.10: trazabilidad de la aceptación explícita cuando falta el CIF de la empresa destino. */
  own_tax_id_exception_accepted: boolean
}
