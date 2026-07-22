// Tipos de dominio del panel de facturas de la asesoría (S3.1).
import type { components } from '../../api/schema'

/** Una fila del panel: una factura confirmada (spec §2). */
export type InvoiceRow = components['schemas']['InvoiceRowOut']

/** Respuesta completa de `GET /reporting/invoices`: una página (spec §2). */
export type PanelPage = components['schemas']['PanelOut']

/** Filtros del panel, todos opcionales y combinables (spec §2). */
export interface PanelFilters {
  date_from?: string
  date_to?: string
  q?: string
  confirmed_by?: string
  cif_status?: string
  company_id?: string
}
