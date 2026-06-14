# ADR-0008: DNS en Hostinger durante el desarrollo (enmienda a ADR-004)

- **Estado**: aceptado
- **Fecha**: 2026-06-13
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: enmienda parcial de **ADR-004** (estrategia de dominios, PLAN MAESTRO §3.3-bis)

## Contexto
ADR-004 fijó usar **Cloudflare** como DNS de `autoken.es` (proxy ON), por tres motivos: certificado
comodín gratuito `*.autoken.es`, escudo proxy (oculta IP de origen, DDoS/WAF gratis) y subdominios de
primer nivel para el modelo multi-tenant.

Al ejecutar la tarea 0.2 surgen dos hechos:
1. Julio no tiene cuenta de Cloudflare y nunca lo ha usado; gestiona con soltura el panel de Hostinger.
2. La creación de la cuenta Cloudflare y el cambio de nameservers son acciones que **solo puede hacer
   Julio** (identidad + acceso al registrador); Claude Code no puede crear la cuenta por él.
3. El dominio `autoken.es` ya usa los nameservers de Hostinger (`aurora`/`nebula.dns-parking.com`), por lo
   que su zona DNS es editable directamente en hPanel sin cambiar nameservers.

Además, el DNS **no está en la ruta crítica** de las tareas inmediatas (0.4–0.7 son locales) y el HTTPS lo
resuelve **Caddy** en el VPS (PLAN MAESTRO §3.1), no dependemos del certificado de Cloudflare.

## Decisión
Durante **desarrollo y staging**, gestionar el DNS de `autoken.es` **directamente en Hostinger**:
- Registros A creados (verificados resolviendo a la IP correcta el 2026-06-14): `setex`, `panel`, `tuti`
  (tenant demo, renombrado por Julio desde el provisional `joseramon`), `setex-staging`, `panel-staging`
  → `2.24.8.109` (VPS B), TTL 300.
- HTTPS gestionado por **Caddy** (Let's Encrypt automático por host) en el VPS B.
- **Antes del go-live** se evaluará migrar el DNS a Cloudflare para recuperar el escudo proxy y el comodín
  (cambio sin impacto en código: solo nameservers). Pendiente registrado como issue de GitHub.

## Alternativas consideradas
- **Cloudflare ahora (ADR-004 literal)**: más pasos para Julio (cuenta + token + cambio de nameservers) sin
  beneficio real en una fase sin datos reales. Se pospone, no se descarta.
- **Comodín `*` en Hostinger ahora**: cubriría todos los subdominios de tenants futuros de golpe, pero
  capturaría también `www`/raíz (que deben quedar libres para la web corporativa). Se opta por registros
  explícitos ahora; el comodín se valorará en Sprint 4 (S4.1 alta de tenant) junto con la migración a
  Cloudflare.

## Consecuencias
- (+) Desbloquea 0.2 de inmediato con la herramienta que Julio domina; cero cambios de código.
- (+) TLS funcional vía Caddy; arquitectura intacta.
- (−) Sin escudo proxy de Cloudflare en desarrollo (irrelevante: staging no tiene datos reales).
- (−) Alta de nuevos tenants requiere añadir su registro A manualmente hasta que haya comodín/Cloudflare.
- Pendiente de go-live: decidir Cloudflare vs comodín Hostinger (issue de seguimiento).
