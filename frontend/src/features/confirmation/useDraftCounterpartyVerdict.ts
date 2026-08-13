// La validación sigue siendo del servidor: el navegador solo presenta su veredicto para el borrador
// actual y nunca persiste nada hasta la confirmación.
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export const DRAFT_COUNTERPARTY_VERDICT_PATH = '/api/v1/uploads/{file_id}/counterparty-verdict'

interface Input {
  fileId: string
  taxId: string
  name: string
  initialTaxId: string
  initialName: string
}

export function useDraftCounterpartyVerdict({ fileId, taxId, name, initialTaxId, initialName }: Input) {
  const [draft, setDraft] = useState({ taxId, name })
  useEffect(() => {
    const timeout = window.setTimeout(() => setDraft({ taxId, name }), 300)
    return () => window.clearTimeout(timeout)
  }, [taxId, name])
  const changed = draft.taxId !== initialTaxId || draft.name !== initialName
  // No consulta un CIF a medio escribir. La pausa además evita lanzar una petición por tecla.
  const enabled = changed && draft.taxId.trim().length >= 9 && draft.name.trim() !== ''

  const query = useQuery({
    queryKey: ['draft-counterparty-verdict', fileId, draft.taxId, draft.name],
    enabled,
    staleTime: 0,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.POST(DRAFT_COUNTERPARTY_VERDICT_PATH, {
        params: { path: { file_id: fileId } },
        body: { counterparty_tax_id: draft.taxId, counterparty_name: draft.name },
      })
      if (error || !data) throw new Error('No se pudo verificar el CIF. Revísalo antes de guardar.')
      return data
    },
  })

  return { ...query, isDebouncing: draft.taxId !== taxId || draft.name !== name }
}
