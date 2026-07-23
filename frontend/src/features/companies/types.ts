// Tipos de dominio de la pantalla "Empresas" (S3.4).
import type { components } from '../../api/schema'

/** Una fila de la ficha agregada de empresas (spec §2/§3 C1). */
export type CompanyRow = components['schemas']['CompanyRowOut']

/** Cuerpo de alta de empresa (reutiliza S1.5 tal cual). */
export type CompanyCreate = components['schemas']['CompanyCreate']

/** Cuerpo de edición de empresa, patch parcial (reutiliza S1.5 tal cual). */
export type CompanyUpdate = components['schemas']['CompanyUpdate']

/** Un registro pendiente de aprobación (reutiliza S1.4 tal cual). */
export type PendingRegistration = components['schemas']['RegistrationOut']
