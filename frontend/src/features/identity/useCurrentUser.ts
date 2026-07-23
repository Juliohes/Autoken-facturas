// Hook de datos de la identidad autenticada (S3.5): consulta `GET /auth/me` (ya existente desde
// S1.6) para saber el rol de quien usa la aplicación. Prerrequisito mínimo para condicionar UI por
// rol (p. ej. la casilla "Factura de prueba", exclusiva de `tenant_admin`); no es el mecanismo de
// sesión/login completo (app-shell), que sigue pendiente como tarea de integración aparte.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useCurrentUser() {
  return useQuery({
    queryKey: ['current-user'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/auth/me')
      if (error || !data) throw new Error('No se pudo cargar la identidad del usuario')
      return data
    },
  })
}
