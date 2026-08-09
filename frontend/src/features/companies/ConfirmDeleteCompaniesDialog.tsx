// Aviso emergente de confirmación antes de borrar empresas seleccionadas (2026-08-09, a petición
// de Julio: "que aparezca... un pequeño botón para hacer check... y eliminar finalmente la
// empresa, tras un aviso emergente para confirmar el borrado"), mismo patrón `role="dialog"` que
// el resto de diálogos del proyecto. Sustituye al `window.confirm` singular de antes: ahora se
// puede borrar más de una empresa a la vez, y un `confirm()` nativo no lista bien varios nombres.
interface Props {
  names: string[]
  deleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDeleteCompaniesDialog({ names, deleting, onConfirm, onCancel }: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirmar borrado de empresas"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md space-y-3 rounded-lg border border-slate-600 bg-slate-800 p-4 text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">
          ¿Borrar {names.length} {names.length === 1 ? 'empresa' : 'empresas'}?
        </h2>
        <p className="text-sm text-red-400">
          Esto borra de forma permanente, junto con su histórico, y no se puede deshacer:
        </p>
        <ul className="max-h-48 list-disc space-y-1 overflow-y-auto pl-5 text-sm text-slate-300">
          {names.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
            className="rounded-md border border-red-500 px-3 py-1.5 text-sm text-red-400 disabled:opacity-40"
          >
            {deleting ? 'Borrando…' : 'Borrar'}
          </button>
        </div>
      </div>
    </div>
  )
}
