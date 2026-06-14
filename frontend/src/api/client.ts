import createClient from 'openapi-fetch'

import type { paths } from './schema'

// Cliente HTTP tipado generado desde el OpenAPI del backend.
// Los tipos viven en ./schema.d.ts (regenerar con `npm run gen:api`).
// baseUrl vacío: las rutas del OpenAPI ya incluyen el prefijo /api/v1.
export const api = createClient<paths>({ baseUrl: '' })
