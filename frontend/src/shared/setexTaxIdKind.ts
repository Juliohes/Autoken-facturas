// Reconocimiento de formato de identificador fiscal (HIPERDOC-FRONTEND-USUARIO-v1-setex1.md §11):
// que el proveedor sea NIF o NIE es una señal de negocio (persona física), no solo cosmética.
// Experimento 2026-08-01, rama experiment/setex-user-ui-v1.
export type TaxIdKind = 'nif' | 'nie' | 'cif' | null

export function setexTaxIdKind(raw: string | null | undefined): TaxIdKind {
  if (!raw) return null
  const value = raw.trim().toUpperCase()
  if (/^\d{8}[A-Z]$/.test(value)) return 'nif'
  if (/^[XYZ]\d{7}[A-Z]$/.test(value)) return 'nie'
  if (/^[A-Z]\d{7}[A-Z0-9]$/.test(value)) return 'cif'
  return null
}

export const TAX_ID_LABEL: Record<Exclude<TaxIdKind, null>, string> = {
  nif: 'NIF',
  nie: 'NIE',
  cif: 'CIF',
}
