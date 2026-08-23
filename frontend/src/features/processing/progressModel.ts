export interface ProgressModel {
  message: string
  subtext: string | null
  percent: number | null
}

const BY_STAGE: Record<string, ProgressModel> = {
  queued: { message: 'En cola', subtext: 'Hemos guardado la factura', percent: 12 },
  loading_document: {
    message: 'Verificando documento',
    subtext: 'Preparando la imagen de forma segura',
    percent: 22,
  },
  primary_ocr: { message: 'Procesando factura', subtext: 'Leyendo los datos', percent: 48 },
  validating: {
    message: 'Comprobando datos',
    subtext: 'Revisando CIF, importes e impuestos',
    percent: 70,
  },
  fallback_ocr: {
    message: 'Verificando una duda',
    subtext: 'Contrastando los campos dudosos',
    percent: 80,
  },
  consensus: {
    message: 'Contrastando resultados',
    subtext: 'Eligiendo el dato más fiable',
    percent: 88,
  },
  persisting: {
    message: 'Casi está',
    subtext: 'Guardando el resultado para revisión',
    percent: 96,
  },
}

const BY_STATUS: Record<string, ProgressModel> = {
  pending_ocr: { message: 'En cola', subtext: 'Hemos guardado la factura', percent: 12 },
  ocr_done: { message: 'Lista para revisar', subtext: null, percent: 100 },
  needs_review: {
    message: 'Lista para revisar',
    subtext: 'Hay algún dato que conviene comprobar',
    percent: 100,
  },
  capture_unreadable: { message: 'Repite la foto', subtext: 'No se pudo leer con fiabilidad', percent: null },
  ocr_failed: { message: 'No pudimos completar la lectura', subtext: 'Puedes reintentar', percent: null },
}

const INDETERMINATE: ProgressModel = {
  message: 'Procesando factura',
  subtext: 'Estamos preparando el resultado',
  percent: null,
}

export function progressModel(status: string, stage?: string | null): ProgressModel {
  if (stage && BY_STAGE[stage]) return BY_STAGE[stage]
  return BY_STATUS[status] ?? INDETERMINATE
}
