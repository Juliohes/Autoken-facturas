# Acceso web a Autofactu

## URLs

| Perfil | URL | Entrada inicial |
|---|---|---|
| Admin de plataforma | `https://panel-staging.autoken.es/login` | `/plataforma` |
| Admin de asesoría | `https://setex.autoken.es/login` | `/facturas` |
| Usuario empleado | `https://setex.autoken.es/login` | `/capturar` |
| Tenant demo | `https://ilex.autoken.es/login` | solo para cuentas con empresa en `ilex` |

El panel de plataforma y el tenant usan el mismo formulario, pero el dominio determina el ámbito de
login. Un `platform_admin` debe iniciar sesión en `panel-staging.autoken.es`; un usuario de asesoría
debe hacerlo en el subdominio de su asesoría.

## Cuentas preparadas

- Plataforma: `juliohesuni@gmail.com` y `albertomurimarti@gmail.com`. Ambas están activas y exigen el
  código TOTP de la aplicación Authenticator. Julio tiene además `is_admin_tech` para las pantallas de
  laboratorio y ajustes técnicos.
- Admin de `setex`: Julio y Alberto tienen una cuenta `tenant_admin` activa en ese tenant. El admin no
  necesita pertenecer a una empresa concreta.
- Usuario de prueba: `soporte@autoken.es` tiene una cuenta `user` activa en `setex`, con la empresa
  **Estudio Inghervi, S.L.U.** (`B06400980`). No tiene TOTP.
- No usar `soporte@autoken.es` en `ilex`: existe una fila histórica sin empresa asignada y el sistema la
  rechaza correctamente al cargar `/auth/me`. Esto evita dejar un usuario sin el scoping obligatorio.

Las contraseñas no se guardan en este repositorio ni se muestran en logs. Usa la contraseña que fijó cada
persona durante su activación. Si una cuenta activada la ha olvidado, el operador debe ejecutar el flujo
de `reset-password` de `backend/scripts/create_account.py` para el ámbito exacto, y la persona debe
completar una nueva activación y TOTP si corresponde.

## Primera prueba

1. Abre una ventana privada o un perfil independiente del navegador para cada rol.
2. Entra en la URL correspondiente y usa el email y contraseña de esa cuenta.
3. Para un admin de plataforma, introduce el código TOTP actual cuando el formulario lo solicite.
4. Comprueba la ruta inicial: `/plataforma`, `/facturas` o `/capturar` según el rol.
5. Cierra sesión antes de probar otro rol en el mismo perfil.

El access token solo vive en memoria. La sesión persistente usa una cookie `httpOnly`, `Secure` y
`SameSite=Strict` limitada al host y a `/api/v1/auth`; por eso no se deben compartir pestañas autenticadas
entre tenants ni usar el panel para entrar como usuario de `setex`.

## Comprobación técnica

```bash
curl -sS https://panel-staging.autoken.es/api/v1/health
curl -sS https://ilex.autoken.es/api/v1/health
curl -sS https://setex.autoken.es/api/v1/health
```

Las tres respuestas deben ser JSON con `"status":"ok"`. Sin sesión, este endpoint debe devolver `401`
JSON, no la página HTML del frontend:

```bash
curl -sS -i https://setex.autoken.es/api/v1/auth/me
```

## Diagnóstico rápido

- `Invalid credentials`: revisa que el dominio corresponde al rol y que la contraseña pertenece a esa
  cuenta y tenant.
- `totp_required`: introduce el código de seis dígitos actual de Authenticator; no se completa con la
  contraseña.
- La página carga pero el login no termina: haz una recarga fuerte y comprueba `/api/v1/health`; si
  devuelve HTML, detén el despliegue y ejecuta `bash infrastructure/deploy.sh` desde la raíz. No
  vuelvas a arrancar solo `docker-compose.yml`: API y worker fallarán cerrados en staging/producción.
- `403` o `Empresa no encontrada` para el usuario: confirma que se está usando `setex.autoken.es`, no
  `ilex.autoken.es`, y que la cuenta conserva exactamente una empresa activa.
- `503`: no repetir intentos indefinidamente; comprobar health de Redis, Postgres, MinIO y ClamAV.
