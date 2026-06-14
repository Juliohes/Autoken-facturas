# Runbook — Provisioning y hardening de VPS (tarea 0.3)

> Estado al 2026-06-14. Acceso por clave SSH dedicada `autoken_deploy` (ed25519).
> Decisiones relacionadas: ADR-0008 (DNS), ADR-0009 (alcance del hardening del VPS A).

## Inventario

| VPS | IP | Rol | Hardening aplicado |
|---|---|---|---|
| B | `2.24.8.109` | Construcción v2 (staging → prod en go-live) | **Completo** |
| A | `72.60.186.89` | v1 de Setex en **producción** | **Mínimo** (solo password-auth off) — ver ADR-0009 |

## Acceso

- Clave de despliegue: `~/.ssh/autoken_deploy` (privada, **nunca** en el repo) + `.pub`.
  Fingerprint: `SHA256:q+czO8aU9tdWWL7p5TzOycrtg5KSOVuHXgiDfPamToM`.
- VPS B: usuario **`deploy`** (sudo NOPASSWD, solo clave). root sin acceso SSH.
- VPS A: se mantiene el acceso existente (root y `devuser` por clave). No se creó usuario nuevo.

## VPS B — `2.24.8.109` (hardening completo)

Aplicado el 2026-06-14:

1. **Usuario `deploy`**: creado, en grupo `sudo`, clave `autoken_deploy.pub` en
   `~/.ssh/authorized_keys`. Sudo sin contraseña en `/etc/sudoers.d/90-deploy`
   (`deploy ALL=(ALL) NOPASSWD:ALL`) — necesario para automatización por clave.
2. **SSH** (`/etc/ssh/sshd_config.d/00-autoken-hardening.conf`):
   `PermitRootLogin no`, `PasswordAuthentication no`, `PubkeyAuthentication yes`,
   `KbdInteractiveAuthentication no`, `X11Forwarding no`, `MaxAuthTries 3`, `AllowUsers deploy`.
   Se neutralizó el `PasswordAuthentication yes` de `50-cloud-init.conf`.
   Validado con `sshd -t` antes de `systemctl reload ssh`.
3. **UFW**: `default deny incoming` / `allow outgoing`; permitidos `22`, `80`, `443` (tcp).
   Activado tras añadir las reglas (sin perder SSH).
4. **fail2ban**: instalado; jail `sshd` en `/etc/fail2ban/jail.d/sshd.local`
   (`maxretry=5`, `findtime=10m`, `bantime=1h`). Activo.
5. **unattended-upgrades**: activo; `20auto-upgrades` (update+upgrade diario) y
   `52autoken-unattended.conf` con reinicio automático a las **04:30**.
6. **root**: contraseña rotada a aleatoria fuerte; guardada **solo** en el propio VPS en
   `/root/.autoken_root_password` (chmod 600). No se usa para login (root SSH deshabilitado).
7. **Docker**: `docker-ce` + `compose` plugin (repo oficial). `deploy` en grupo `docker`.
   Versiones: Docker 29.5.3, Compose v5.1.4.

### Verificación VPS B
- `ssh deploy@2.24.8.109` por clave → OK; root y password → denegados.
- `sshd -T` → `permitrootlogin no`, `passwordauthentication no`, `allowusers deploy`.
- UFW activo (22/80/443); fail2ban activo; unattended-upgrades activo.
- `docker ps` como `deploy` sin sudo → OK.

## VPS A — `72.60.186.89` (hardening MÍNIMO)

Ver **ADR-0009** para la justificación. Sólo se aplicó:

- **SSH** (`/etc/ssh/sshd_config.d/00-autoken-hardening.conf`): `PasswordAuthentication no`,
  `KbdInteractiveAuthentication no`. Se neutralizó el `yes` de `50-cloud-init.conf`.
  Validado con `sshd -t` + `reload`. **No** se tocó: usuarios, `PermitRootLogin`
  (sigue `without-password`/solo-clave), UFW, ni la contraseña root.

### Por qué mínimo (resumen — detalle en ADR-0009)
- El riesgo original del plan (login root por contraseña) **ya no aplicaba**: root ya era solo-clave,
  con fail2ban y unattended-upgrades instalados.
- Es producción con un operador activo (`devuser`); la estrategia acordada es **construir todo en VPS B**
  y retirar el VPS A tras la migración. No se justifica el riesgo de un hardening completo en producción.

### Hallazgos de seguridad (informativos, sin actuar)
- Puerto **`2222`** publica a Internet el SSH del contenedor `setex-prod-backend`
  (`0.0.0.0:2222->22`). Pendiente de revisar con Julio (cerrarlo implica tocar la v1).
- Conviven en producción contenedores `setex-prod-*` y `setex-staging-*` (el staging de la v1 vive en la
  máquina de producción). No se modifica.
- Usuarios preexistentes: `ubuntu`, `setex` (sin clave, pass bloqueada), `devuser` (3 claves, activo),
  `deploy` y `claude` (preexistentes, no creados en esta tarea).

### Verificación VPS A
- `ssh root@72.60.186.89` por clave → OK (sin lockout); password → denegado.
- Sesiones tmux de `devuser` intactas tras el `reload`.

## Notas operativas
- El firewall de VPS A no se gestiona con UFW (host Docker: Docker manipula iptables y se salta UFW). Si se
  requiere firewall en A en el futuro, usar `ufw-docker` o el firewall del proveedor — fuera de 0.3.
- Rotación futura de la clave `autoken_deploy`: generar nueva, añadir `.pub` a `~deploy/.ssh/authorized_keys`
  (B) y `~/.ssh/authorized_keys` (A, root), verificar acceso, y retirar la antigua.
