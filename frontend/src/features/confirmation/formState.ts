// Estado editable del formulario de confirmación y su proyección al body de
// `POST confirm` (spec §2, C8; ampliado spec S6.1: número de factura + coma decimal).
// Lógica pura, separada del componente y testeable.
import { formatIvaPercentage } from './percentage'
import type { ConfirmBody, ReviewFields, ReviewResponse, ReviewTaxLine } from './types'

/** Un tramo de IVA editable en el formulario (strings de los inputs). */
export interface TaxLineForm {
  iva_pct: string
  base: string
  cuota: string
}

/** Estado editable de la pantalla (valores mostrados, ya editados por el humano). */
export interface ConfirmFormState {
  issue_date: string
  counterparty_tax_id: string
  counterparty_name: string
  invoice_number: string
  net_amount: string
  tax_amount: string
  total_amount: string
  irpf_amount: string
  tax_lines: TaxLineForm[]
}

/** Convierte un valor leído (`string | null`) al string editable del input. */
function toInput(value: string | null | undefined): string {
  return value ?? ''
}

/**
 * Convierte un importe leído (punto decimal, formato del backend) a coma decimal para mostrarlo
 * (spec S6.1 C16): "121.45" -> "121,45"; sin parte decimal, no añade ninguna ("121" -> "121").
 */
function toAmountInput(value: string | null | undefined): string {
  return toInput(value).replace('.', ',')
}

/** Convierte un valor de tramo (número o string del OCR) al string editable, con coma (C16). */
function taxCellToAmountInput(value: number | string | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value)
  return text.replace('.', ',')
}

/** Un string vacío se envía como `null` (campo no leído, regla 4: no se inventa). */
function toBody(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

// Una coma seguida de 1-2 dígitos es inequívocamente decimal ("121,45"); 3 o más dígitos son
// ambiguos (¿decimal de 3 cifras, o una coma de miles tecleada por error, ej. "1,234" queriendo
// decir 1234?). Auditoría (2026-08-08): convertir esa coma a ciegas colaría un importe ~1000x
// distinto del querido, aceptado en silencio por `Decimal` sin ningún error.
const UNAMBIGUOUS_COMMA_DECIMAL = /^-?\d+,\d{1,2}$/

/**
 * Un importe editado (con coma o, por costumbre, con punto — C17) al punto decimal que espera el
 * backend (C18); vacío -> `null`. Una coma ambigua (posible separador de miles) NO se convierte:
 * se envía tal cual para que el backend la rechace con un error claro, en vez de aceptar en
 * silencio un importe equivocado (hallazgo de auditoría, ver `UNAMBIGUOUS_COMMA_DECIMAL`).
 */
function toAmountBody(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  return UNAMBIGUOUS_COMMA_DECIMAL.test(trimmed) ? trimmed.replace(',', '.') : trimmed
}

/** Construye el estado editable inicial desde los campos de la revisión. */
export function reviewToFormState(fields: ReviewFields): ConfirmFormState {
  return {
    issue_date: toInput(fields.issue_date),
    counterparty_tax_id: toInput(fields.counterparty_tax_id),
    counterparty_name: toInput(fields.counterparty_name),
    // Número de factura: como el CIF, sin formato de importe (spec S6.1 C19).
    invoice_number: toInput(fields.invoice_number),
    net_amount: toAmountInput(fields.net_amount),
    tax_amount: toAmountInput(fields.tax_amount),
    total_amount: toAmountInput(fields.total_amount),
    irpf_amount: '',
    tax_lines: (fields.tax_lines ?? []).map(taxLineToForm),
  }
}

/**
 * Adapta un tramo del OCR (`base/rate/cuota`) al tramo editable (`iva_pct/base/cuota`).
 * `iva_pct` usa `formatIvaPercentage` (nunca ".0"/",0" superfluo, ej. "21%" no "21,0%",
 * petición de Julio 2026-07-22); `base`/`cuota` con coma decimal (spec S6.1 C16).
 */
function taxLineToForm(line: ReviewTaxLine): TaxLineForm {
  return {
    iva_pct: formatIvaPercentage(line.rate),
    base: taxCellToAmountInput(line.base),
    cuota: taxCellToAmountInput(line.cuota),
  }
}

/**
 * Proyecta el estado editado al body de `POST confirm` (C8). `direction` la fija
 * quien orquesta (la selección Recibida/Emitida es de S2.2, aquí se propaga).
 */
export function formStateToConfirmBody(
  form: ConfirmFormState,
  options: {
    direction: ConfirmBody['direction']
    responsibilityAccepted: boolean
    isTest?: boolean
  },
): ConfirmBody {
  return {
    direction: options.direction,
    issue_date: toBody(form.issue_date),
    counterparty_tax_id: toBody(form.counterparty_tax_id),
    counterparty_name: toBody(form.counterparty_name),
    invoice_number: toBody(form.invoice_number),
    net_amount: toAmountBody(form.net_amount),
    tax_amount: toAmountBody(form.tax_amount),
    total_amount: toAmountBody(form.total_amount),
    irpf_amount: toAmountBody(form.irpf_amount),
    tax_lines: form.tax_lines.map((line) => ({
      iva_pct: toBody(line.iva_pct),
      base: toAmountBody(line.base),
      cuota: toAmountBody(line.cuota),
    })),
    responsibility_accepted: options.responsibilityAccepted,
    is_test: options.isTest ?? false,
  }
}

/** Atajo: estado editable inicial a partir de la respuesta completa de review. */
export function initialFormState(review: ReviewResponse): ConfirmFormState {
  return reviewToFormState(review.fields)
}
