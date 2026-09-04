import type { components } from '../../api/schema'
import type { Direction } from '../capture/types'

// S6.12 publica solo metadatos operativos de los envíos: nunca datos de contraparte.
// `direction` y los estados S6.13 son opcionales hasta regenerar OpenAPI; su ausencia representa
// histórico previo y se pide a la persona, nunca se rellena con un valor inventado.
export type HistoryEntry = components['schemas']['HistoryEntryOut'] & {
  direction?: Direction | null
}
export type HistoryResponse = Omit<components['schemas']['HistoryOut'], 'entries'> & {
  entries: HistoryEntry[]
}

// Filtro de periodo del historial (bloque D, PROMPT-AUTOFACTU-AJUSTES-v3): filtra server-side por
// la fecha de la propia factura (invoice_date), con trimestres naturales.
export type HistoryPeriod = 'total' | 'month' | 'quarter' | 'year'
