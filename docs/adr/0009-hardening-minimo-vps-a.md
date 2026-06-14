# ADR-0009: Hardening mínimo del VPS A (producción), construir todo en VPS B

- **Estado**: aceptado
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: matiza la tarea 0.3 del PLAN MAESTRO y la asignación de VPS de ADR-005 (§5.1)

## Contexto
La tarea 0.3 pedía endurecer **ambos** VPS. La justificación para el VPS A (`72.60.186.89`, v1 en
producción) era, según el PLAN MAESTRO §0-BIS, que tenía "login root por contraseña" circulada, a eliminar
y rotar.

Al ejecutar 0.3, el reconocimiento (solo lectura) del VPS A mostró que la realidad difiere del plan:
- **root ya entra solo con clave** (`PermitRootLogin without-password`); el riesgo original ya estaba mitigado.
- `fail2ban` y `unattended-upgrades` ya instalados.
- Hay un operador **activo**: `devuser` (3 claves) con sesiones tmux abiertas desde semanas atrás.
- Es un **host Docker** con Traefik sirviendo la v1; conviven contenedores `setex-prod-*` y
  `setex-staging-*`. Docker gestiona iptables directamente, por lo que **UFW no filtraría** los puertos
  publicados y daría falsa seguridad (además rompería el puerto `2222`, ver hallazgos).
- Existen usuarios preexistentes (`deploy`, `claude`) no creados por esta tarea.

Julio confirma la estrategia: **construir el sistema v2 completamente en el VPS B** y **retirar la app del
VPS A tras la migración**. No quiere arriesgar producción con cambios innecesarios.

## Decisión
- **VPS B**: hardening **completo** (ver runbook `provisioning.md`).
- **VPS A**: hardening **mínimo de acceso**, solo `PasswordAuthentication no` (forzar clave), validado y sin
  cortar sesiones. **No** se tocan: usuarios, `PermitRootLogin` (sigue solo-clave), UFW, ni la contraseña
  root. Cualquier otra acción sobre VPS A requiere OK explícito de Julio.
- El VPS A se endurecerá por completo **cuando se retire la v1** y se limpie (sin producción encima).

## Alternativas consideradas
- **Hardening completo de A ahora**: riesgo real de lockout del operador activo y de romper la v1 (UFW en
  host Docker, `AllowUsers`, rotación). Beneficio bajo porque A se va a retirar. Descartado.
- **No tocar A en absoluto**: válido, pero forzar clave (desactivar password-auth) es de riesgo nulo y
  cierra una vía de fuerza bruta. Se opta por este mínimo.

## Consecuencias
- (+) Producción intacta y sin riesgo; operador activo conserva acceso por clave.
- (+) VPS B totalmente endurecido y listo para construir la v2.
- (−) VPS A no tiene firewall propio gestionado por nosotros (se confía en el proveedor + Docker) hasta su
  retirada.
- **Hallazgos abiertos (informativos)**: puerto `2222` expone el SSH del contenedor `setex-prod-backend` a
  Internet; staging de la v1 corre en la máquina de producción. Revisar con Julio antes de actuar (implican
  tocar la v1).
