// Tipos de dominio del tenant resuelto por subdominio + su branding (S1.2/S4.2).
import type { components } from '../../api/schema'

/** Respuesta de `GET /tenants/current`: datos públicos del tenant + su branding (o `null`). */
export type CurrentTenant = components['schemas']['TenantCurrentOut']
