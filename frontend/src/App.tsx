import { useHealth } from './api/health'
import { useTenantTheme } from './features/tenancy/useTenantTheme'

// Pantalla mínima de la Fase 0: comprueba la conexión con el backend
// mediante el cliente OpenAPI autogenerado (healthcheck).
export default function App() {
  const { data, isLoading, isError } = useHealth()
  const theme = useTenantTheme()

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-900 text-slate-100">
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-8 shadow-lg text-center">
        {theme.logoUrl && (
          // `referrerPolicy="no-referrer"`: el logo lo aloja el propio tenant (URL de terceros
          // potencialmente), evita filtrar el Referer (con el subdominio del tenant) a ese host.
          <img
            src={theme.logoUrl}
            alt={theme.appName}
            referrerPolicy="no-referrer"
            className="mx-auto mb-4 max-h-16"
          />
        )}
        <h1 className="text-2xl font-semibold mb-4">Autoken Facturas v2</h1>

        {isLoading && <p className="text-slate-400">Comprobando backend…</p>}

        {isError && (
          <p className="text-red-400">No se pudo conectar con el backend.</p>
        )}

        {data && (
          <dl className="text-left text-sm space-y-1">
            <div className="flex gap-2">
              <dt className="text-slate-400">Estado:</dt>
              <dd className="text-emerald-400 font-medium">{data.status}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-slate-400">Servicio:</dt>
              <dd>{data.service}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-slate-400">Versión:</dt>
              <dd>{data.version}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-slate-400">Entorno:</dt>
              <dd>{data.environment}</dd>
            </div>
          </dl>
        )}
      </div>
    </main>
  )
}
