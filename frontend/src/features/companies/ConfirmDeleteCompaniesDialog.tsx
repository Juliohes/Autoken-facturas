import { Modal } from '../../shared/Modal'

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
    <Modal
      title={`¿Borrar ${names.length} ${names.length === 1 ? 'empresa' : 'empresas'}?`}
      accessibleName="Confirmar borrado de empresas"
      onClose={onCancel}
      panelClassName="max-w-md space-y-3"
    >
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
    </Modal>
  )
}
