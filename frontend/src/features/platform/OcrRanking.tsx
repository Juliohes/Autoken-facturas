// Pantalla del ranking multi-modelo (S4.8): agregado por motor, ordenado por puntuación media
// (ya lo devuelve así el backend). Solo lectura, sin gráficas ni historial (spec §6).
import { useSession } from '../session/SessionProvider'
import { useOcrRanking } from './useOcrRanking'

// Asimetría de motores documentada en la spec (§0): Azure DocIntel y Mistral OCR4 NO son modelos de
// lenguaje "promptables" (no se les puede pedir un JSON de campos); Azure mapea su propio esquema de
// `prebuilt-invoice`, y Mistral es OCR puro (siempre devuelve campos vacíos, por diseño de su API, no
// un fallo del motor). La spec exige que el panel muestre esta distinción, no solo el código.
const ENGINES_SIN_CAMPOS_PROMPTABLES = new Set(['azure-docintel', 'mistral-ocr-4'])

export function OcrRanking() {
  const { user } = useSession()
  // Mismo criterio que PlatformSettings (S4.10, hallazgo de auditoría): evita un GET que el
  // backend rechazaría de todos modos (403) cuando el usuario no tiene el flag.
  const ranking = useOcrRanking(user?.is_admin_tech ?? false)

  // C10: un platform_admin sin el flag nunca ve el ranking, aunque entre a la URL a mano — la
  // ruta ya está protegida por rol (app/routes.ts); esta comprobación es la del flag en sí.
  if (!user?.is_admin_tech) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No tienes acceso a esta pantalla.
        </p>
      </div>
    )
  }

  return (
    <section className="mx-auto max-w-3xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Ranking OCR multi-modelo</h1>
      <p className="text-sm text-slate-400">
        Puntuación media de cada motor candidato sobre las facturas ya procesadas con el
        experimento activo, ordenado de mejor a peor.
      </p>

      {ranking.isLoading && <p className="text-slate-400">Cargando…</p>}

      {ranking.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el ranking. Inténtalo de nuevo.
        </p>
      )}

      {ranking.data && ranking.data.length === 0 && (
        <p className="text-slate-400">
          Todavía no hay facturas rankeadas (el experimento sigue apagado o no ha procesado nada
          aún).
        </p>
      )}

      {ranking.data && ranking.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400">
                <th className="py-2 pr-4">Motor</th>
                <th className="py-2 pr-4">Facturas leídas</th>
                <th className="py-2 pr-4">Puntuación media</th>
                <th className="py-2 pr-4">Primer puesto</th>
              </tr>
            </thead>
            <tbody>
              {ranking.data.map((row) => (
                <tr key={row.engine} className="border-b border-slate-800">
                  <td className="py-2 pr-4 font-medium">
                    {row.engine}
                    {ENGINES_SIN_CAMPOS_PROMPTABLES.has(row.engine) && (
                      <span
                        className="ml-2 text-xs font-normal text-slate-500"
                        title="Este motor no es un modelo de lenguaje promptable: sus campos vienen de su propio esquema (Azure DocIntel) o siempre están vacíos por diseño de su API (Mistral OCR4), no por un fallo de lectura."
                      >
                        (sin campos estructurados por diseño de su API)
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4">{row.invoices_read}</td>
                  <td className="py-2 pr-4">{row.average_score.toFixed(2)}</td>
                  <td className="py-2 pr-4">{row.first_place_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
