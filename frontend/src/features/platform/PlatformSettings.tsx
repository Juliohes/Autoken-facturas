// Pantalla de ajustes de plataforma (S4.10): hoy, un único interruptor — el experimento OCR que
// gobernará S2.9/S2.10/S4.8 (tareas futuras, todavía sin enganchar a nada real). Comportamientos
// C8-C10 de la spec.
import { useSession } from '../session/SessionProvider'
import { useAdminSettings } from './useAdminSettings'
import { useUpdateAdminSettings } from './useUpdateAdminSettings'

export function PlatformSettings() {
  const { user } = useSession()
  // `enabled` evita una petición GET que el backend rechazaría de todos modos (403) cuando el
  // usuario no tiene el flag: no es una fuga (el backend ya deniega correctamente), pero ahorra una
  // llamada de red visible en el inspector que delataba la existencia del endpoint sin necesidad
  // (hallazgo de auditoría S4.10).
  const settings = useAdminSettings(user?.is_admin_tech ?? false)
  const update = useUpdateAdminSettings()

  // C9: un platform_admin sin el flag nunca ve el interruptor, aunque entre a la URL a mano — la
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
    <section className="mx-auto max-w-xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Ajustes de plataforma</h1>

      {settings.isLoading && <p className="text-slate-400">Cargando…</p>}

      {settings.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el ajuste. Inténtalo de nuevo.
        </p>
      )}

      {settings.data && (
        <label className="flex items-center gap-3 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={settings.data.ocr_experiment_enabled}
            disabled={update.isPending}
            onChange={(e) => update.mutate(e.target.checked)}
          />
          Experimento OCR (preprocesado + comparativa multi-modelo)
        </label>
      )}

      {update.isError && (
        <p role="alert" className="text-sm text-red-400">
          No se pudo cambiar el ajuste. Inténtalo de nuevo.
        </p>
      )}
    </section>
  )
}
