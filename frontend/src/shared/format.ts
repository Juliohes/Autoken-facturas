// Utils de formato compartidos por toda la app (fechas e importes), a petición de Julio
// (2026-08-01): ningún sitio debía formatear estos valores por su cuenta con `toFixed`/ISO crudo.

/** Fecha + hora:minuto legibles, SIN segundos por defecto (p. ej. "01/08/2026, 13:45"). Devuelve
 * `fallback` ("Sin actividad" por defecto) si no hay valor o no es una fecha válida. */
export function formatDateTime(
  value: string | null | undefined,
  options: { seconds?: boolean; fallback?: string } = {},
): string {
  const { seconds = false, fallback = 'Sin actividad' } = options
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return fallback
  // `timeZone` fijo (no el del servidor/navegador): la app es de asesorías españolas, la hora debe
  // leerse siempre en hora peninsular, sin importar dónde corra el backend o el cliente.
  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: seconds ? '2-digit' : undefined,
    hour12: false,
    timeZone: 'Europe/Madrid',
  }).format(date)
}

/** Solo fecha (día/mes/año), sin hora — para fechas de alta u otras donde la hora no aporta. */
export function formatDate(
  value: string | null | undefined,
  options: { fallback?: string } = {},
): string {
  const { fallback = '—' } = options
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return fallback
  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Europe/Madrid',
  }).format(date)
}

/** Importe con coma decimal y punto de millar (formato español, p. ej. "1.234,56"), nunca con
 * punto para los decimales. `null`/`undefined`/no numérico -> `fallback` ("—" por defecto). */
export function formatCurrency(
  value: number | string | null | undefined,
  options: { fallback?: string } = {},
): string {
  const { fallback = '—' } = options
  if (value === null || value === undefined || value === '') return fallback
  const numeric = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(numeric)) return fallback
  return new Intl.NumberFormat('es-ES', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(numeric)
}

// Una coma seguida de 1-2 dígitos es inequívocamente decimal ("121,45"); 3+ dígitos son ambiguos
// (¿decimal de 3 cifras real, o una coma de miles tecleada por error, ej. "1,234" queriendo decir
// 1234?) — no se convierte a ciegas (hallazgo de auditoría S6.1, 2026-08-08).
const UNAMBIGUOUS_COMMA_DECIMAL = /^-?\d+,\d{1,2}$/

/**
 * Importe del backend (punto decimal) a coma decimal para un INPUT EDITABLE (a diferencia de
 * `formatCurrency`, pensada para lectura: no fuerza 2 decimales ni separador de miles, para no
 * alterar lo que el usuario ve tal cual lo tecleó o lo leyó la IA). `null`/`undefined` -> `''`
 * (campo vacío, no "null" literal).
 *
 * Única fuente de esta conversión en toda la app (2026-08-08, hallazgo de Julio: la misma
 * conversión se había escrito ya una vez en `confirmation/formState.ts` y el resto de pantallas
 * con importes editables —`InvoicesPanel`, `TaxLinesModal`— seguían mostrando el punto crudo del
 * backend porque nunca la reutilizaron). Toda pantalla con un importe editable debe usar esta
 * función, nunca reimplementar `.replace('.', ',')` por su cuenta.
 */
export function toAmountInputValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return ''
  return String(value).replace('.', ',')
}

/**
 * Un importe editado (con coma, o con punto por costumbre — se tolera) al punto decimal que
 * espera el backend; vacío -> `null`. Una coma ambigua (posible separador de miles, 3+ dígitos
 * detrás) NO se convierte: se envía tal cual para que el backend la rechace con un error claro en
 * vez de aceptar en silencio un importe ~1000x distinto del querido. Contrapartida de
 * `toAmountInputValue`, misma fuente única.
 */
export function fromAmountInputValue(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  return UNAMBIGUOUS_COMMA_DECIMAL.test(trimmed) ? trimmed.replace(',', '.') : trimmed
}
