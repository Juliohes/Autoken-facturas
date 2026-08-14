import type { components } from '../../api/schema'

// S6.12 publica solo metadatos operativos de los envíos: nunca datos de contraparte.
export type HistoryEntry = components['schemas']['HistoryEntryOut']
export type HistoryResponse = components['schemas']['HistoryOut']
