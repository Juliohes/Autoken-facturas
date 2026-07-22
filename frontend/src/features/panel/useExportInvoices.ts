// Hook de datos del export a Excel (S3.2): pide GET /reporting/invoices/export
// con los filtros actuales del panel (sin cursor: el export no pagina) y
// dispara la descarga del navegador. Separado de la presentación, mismo
// patrón que useDownloadUrl.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { PanelFilters } from './types'

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function useExportInvoices() {
  return useMutation({
    mutationFn: async (filters: PanelFilters) => {
      const { data, error } = await api.GET('/api/v1/reporting/invoices/export', {
        params: { query: filters },
        parseAs: 'blob',
      })
      if (error || !data) throw new Error('No se pudo generar el Excel')
      triggerDownload(data as Blob, 'facturas.xlsx')
    },
  })
}
