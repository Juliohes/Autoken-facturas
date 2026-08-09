// Ventana con hasta 5 lecturas reales de un motor concreto del Ranking OCR (2026-08-09, a petición
// de Julio: "más contexto, ver ejemplos concretos, no solo números"), mismo patrón de diálogo que
// el resto del proyecto (`TaxLinesModal`/`PlatformLab`). El backend ya redacta el CIF/nombre de
// contraparte de la respuesta (dato identificable de un cliente real, S5.2 §6); este componente no
// necesita filtrar nada más, solo mostrar lo que llega.
import { useOcrRankingExamples } from './useOcrRankingExamples'

interface Props {
  engine: string
  onClose: () => void
}

/** Un valor de `reading` puede ser escalar (importe, fecha...) o anidado (`tax_lines`,
 * `confidences`): `String(value)` sobre un objeto/array da "[object Object]", así que se
 * serializa a JSON en ese caso para que siga siendo legible. */
function formatReadingValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function ExamplesModal({ engine, onClose }: Props) {
  const examples = useOcrRankingExamples(engine)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Ejemplos de ${engine}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-600 bg-slate-800 p-4 text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Ejemplos de {engine}</h2>
          <button type="button" onClick={onClose} className="text-sm text-slate-400 underline">
            Cerrar
          </button>
        </div>

        {examples.isLoading && <p className="text-slate-400">Cargando…</p>}
        {examples.isError && (
          <p role="alert" className="text-red-400">
            No se pudieron cargar los ejemplos de este motor.
          </p>
        )}
        {examples.data && examples.data.length === 0 && (
          <p className="text-slate-400">
            Todavía no hay ejemplos de {engine} (no ha leído ninguna factura con el experimento
            encendido).
          </p>
        )}
        {examples.data && examples.data.length > 0 && (
          <ul className="space-y-3">
            {examples.data.map((ex) => (
              <li
                key={ex.uploaded_file_id}
                className="rounded border border-slate-700 bg-slate-900 p-2"
              >
                <p className="text-xs text-slate-400">
                  Modelo: {ex.model} — puntuación: {ex.score}
                </p>
                <ul className="mt-1 space-y-0.5 text-sm text-slate-300">
                  {Object.entries(ex.reading).map(([field, value]) => (
                    <li key={field}>
                      <span className="font-medium">{field}:</span> {formatReadingValue(value)}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
