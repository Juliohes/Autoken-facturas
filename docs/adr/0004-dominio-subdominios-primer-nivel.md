# ADR-0004: Un solo dominio `autoken.es` con subdominios de primer nivel

- **Estado**: aceptado (matizado por ADR-0008 sobre el proveedor de DNS durante el desarrollo)
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §3.3-bis

## Contexto
La plataforma es multi-tenant white-label. Cada asesoría necesita su espacio aislado y, idealmente, su propia
"app". Hay que elegir cómo mapear tenants a URLs: subdominios (`<asesoria>.autoken.es`) frente a rutas
(`autoken.es/<asesoria>/...`). Ya se dispone del dominio `autoken.es` (no se compra ninguno nuevo).

## Decisión
Un **único dominio `autoken.es`** con **subdominios de primer nivel** por tenant y función:
`setex.autoken.es`, `tuti.autoken.es` (demo), `<asesoria>.autoken.es` (futuras), `panel.autoken.es`
(plataforma), `setex-staging` / `panel-staging` (staging). `autoken.es` y `www` quedan libres para la web
corporativa. El dominio actual de la v1, `setex-facturas.es`, se mantiene como **custom domain** del tenant
Setex para no cambiar la URL a sus usuarios.

## Alternativas consideradas
- **Rutas (`autoken.es/facturas/...`)**: acoplan todos los productos al mismo origen; cookies, CORS y CSP
  compartidos rompen el modelo de aislamiento por host. Descartado.
- **Un dominio por asesoría**: caro y operativamente pesado; el white-label se cubre con subdominios +
  custom domains opcionales.

## Consecuencias
- (+) Aislamiento por host: cookies, CORS y CSP separados por asesoría.
- (+) El certificado comodín `*.autoken.es` cubre exactamente un nivel; nuevas apps = nuevos subdominios.
- (+) Futuras asesorías sin tocar código (junto con S4.1).
- (−) La resolución de tenant por subdominio debe ser sólida en el middleware (S1.2).
- **Nota**: el **proveedor de DNS** durante el desarrollo es Hostinger, no Cloudflare (ver **ADR-0008**); la
  estrategia de subdominios de este ADR no cambia.
