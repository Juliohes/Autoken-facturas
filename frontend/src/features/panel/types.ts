// Tipos de dominio del panel de facturas de la asesoría (S3.1).
import type { components } from '../../api/schema'

/** Una fila del panel: una factura confirmada (spec §2). */
export type InvoiceRow = components['schemas']['InvoiceRowOut']

/** Respuesta completa de `GET /reporting/invoices`: una página (spec §2). */
export type PanelPage = components['schemas']['PanelOut']

/** Cuerpo de `PATCH /invoices/{id}` (S3.3, editable desde el panel a partir de 2026-08-01). */
export type InvoiceEditIn = components['schemas']['InvoiceEditIn']

/** Filtros del panel, todos opcionales y combinables (spec §2).
 *
 * `counterparty_tax_id`: filtro EXACTO por CIF de contraparte (S5.2 C5). Sustituye al antiguo `q`
 * de texto libre por nombre, retirado porque el nombre de contraparte vive cifrado en Postgres sin
 * índice ciego desde S5.2 (decisión de Julio): sin descifrar fila a fila no hay subcadena posible.
 */
export interface PanelFilters {
  date_from?: string
  date_to?: string
  counterparty_tax_id?: string
  confirmed_by?: string
  cif_status?: string
  company_id?: string
}
