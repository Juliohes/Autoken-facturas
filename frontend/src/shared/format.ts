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
