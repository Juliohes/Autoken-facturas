// Tipos de dominio del panel de plataforma (S4.1).
import type { components } from '../../api/schema'

/** Un tenant en la respuesta (alta o listado, spec §3). */
export type Tenant = components['schemas']['TenantOut']

/** Cuerpo de alta de un tenant (spec §2/§3). */
export type TenantCreate = components['schemas']['TenantCreateIn']
