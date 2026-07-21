// Tipos de dominio del historial de facturas (S2.6).
import type { components } from '../../api/schema'

/** Una entrada del historial: factura confirmada de los últimos 7 días (spec §2). */
export type HistoryEntry = components['schemas']['HistoryEntryOut']

/** Respuesta completa de `GET /invoices/history` (spec §2). */
export type HistoryResponse = components['schemas']['HistoryOut']
