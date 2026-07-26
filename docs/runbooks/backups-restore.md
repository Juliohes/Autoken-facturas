# Runbook — Backups de la base de datos y restore drill (S5.3)

> Ver spec `docs/specs/S5.3-backups-restore-drill.md` y `docs/adr/0019-cifrado-y-alcance-backup-base-de-datos.md`.
> Estado a 2026-07-26: el **mecanismo** (backup cifrado + restore drill) está construido y verificado
> empíricamente contra Postgres real de este entorno de trabajo. El **cron nocturno real en la VPS de
> producción** y la **subida a un destino externo real (Hetzner u otro)** están pendientes de una
> sesión futura con esas credenciales — decisión de alcance explícita de Julio, ver spec §0.

## Qué hace cada pieza

- `backend/src/shared/backup_encryption.py`: cifra/descifra el fichero de volcado con AES-256-GCM.
  Clave: `BACKUP_ENCRYPTION_KEY` — **secreto DISTINTO** de `DB_ENCRYPTION_MASTER_KEY` (S5.2, ver
  ADR-0019 para el motivo).
- `backend/src/jobs/backup.py` (`create_encrypted_backup`): ejecuta `pg_dump --format=custom` contra
  el DSN admin de origen, cifra el resultado EN MEMORIA (nunca escribe el volcado en claro en disco)
  y lo escribe de forma atómica (fichero temporal + `os.replace`) en la ruta final.
- `backend/src/jobs/restore_drill.py` (`run_restore_drill`): comprueba que la base de datos destino
  está completamente vacía (si no, se niega a tocarla), descifra el backup y lo restaura con
  `pg_restore`, midiendo el tiempo y devolviendo el recuento de filas de cada tabla restaurada.
- `backend/scripts/backup_database.py` / `backend/scripts/restore_drill.py`: CLIs finas sobre lo
  anterior, pensadas para invocarse desde cron/CI.

## Requisito de sistema: `pg_dump`/`pg_restore` en el PATH

`backend/Dockerfile` tiene un target **`ops`** separado (`docker build --target ops`) que instala
`postgresql-client` — NUNCA en la imagen `api` por defecto (la que sirve tráfico HTTP y el worker
OCR), a propósito (hallazgo de auditoría): un RCE contra el contenedor expuesto a internet no debe
heredar de regalo la herramienta ni la superficie extra de `pg_dump`/`pg_restore`. Para lanzar el
backup real:

```bash
docker build --target ops -t autoken/ops:latest ./backend
docker run --rm \
    -e BACKUP_DATABASE_ADMIN_DSN="postgresql://postgres:...@postgres:5432/autoken" \
    -e BACKUP_ENCRYPTION_KEY="<secreto real>" \
    --network <red-de-compose-donde-vive-postgres> \
    -v /ruta/segura/en/el/host:/backups \
    autoken/ops:latest scripts/backup_database.py --output /backups/autoken-$(date +%F).enc
```

Fuera de Docker (cron del sistema operativo directamente en la VPS), instalar `postgresql-client` en
ese host, no en la imagen de la API.

## ⚠️ Aislamiento de secretos: `BACKUP_ENCRYPTION_KEY`/los DSN admin NUNCA en el `.env` compartido

`docker-compose.yml` monta `env_file: ../.env` (el fichero ENTERO, sin lista blanca) tanto en `api`
como en `worker`. Si `BACKUP_ENCRYPTION_KEY`/`BACKUP_DATABASE_ADMIN_DSN`/`RESTORE_DRILL_TARGET_DSN`
se añaden a ese mismo `.env`, terminan también en el entorno de la API y el worker — aunque ninguno
de los dos los usa nunca — deshaciendo el aislamiento de secretos que es la razón de ser de
ADR-0019 (un RCE en la API ya no comprometería solo `DB_ENCRYPTION_MASTER_KEY`, sino también el
cifrado de los backups y potencialmente el DSN de superusuario). Por eso `backup_encryption_key` NO
es un `model_validator` global de `Settings` (a diferencia de `jwt_secret`/`db_encryption_master_key`):
la API/worker arrancan sin él. **Estos 3 secretos viven en un fichero de entorno APARTE**, leído solo
al invocar los scripts de backup (p. ej. `--env-file /root/.env.backups` en el `docker run` de
arriba, o exportado a mano en la sesión de cron), nunca en `../.env`.

## Uso manual (verificación / operación puntual)

```bash
# Backup (DSN admin del origen SIEMPRE por env var, nunca argumento — visible en `ps` si no).
BACKUP_DATABASE_ADMIN_DSN="postgresql://postgres:...@host:5432/autoken" \
BACKUP_ENCRYPTION_KEY="<secreto real>" \
    python scripts/backup_database.py --output /ruta/segura/autoken-2026-07-26.enc

# Restore drill (la base de datos destino debe existir de antemano y estar VACÍA — crearla es un
# paso manual explícito, el script se niega a tocar una base con tablas).
createdb -h host -U postgres autoken_restore_drill
RESTORE_DRILL_TARGET_DSN="postgresql://postgres:...@host:5432/autoken_restore_drill" \
BACKUP_ENCRYPTION_KEY="<mismo secreto>" \
    python scripts/restore_drill.py --backup-file /ruta/segura/autoken-2026-07-26.enc
# Imprime JSON: duration_seconds, backup_size_bytes, row_counts por tabla.
dropdb -h host -U postgres autoken_restore_drill   # limpieza tras verificar
```

## Medición empírica (verificación de esta tarea, 2026-07-26)

Contra Postgres 16 real de este entorno de trabajo (no una estimación), con 20 asesorías sembradas
(20 tenants + 20 empresas con CIF cifrado, S5.2 + 20 usuarios):

- **Backup**: 86 115 bytes cifrados, **0.35 s**.
- **Restore drill**: **1.10 s** hasta tener la base de datos destino lista, con los mismos recuentos
  de filas que el origen en las 17 tablas del esquema (20 tenants, 20 companies, 20 users, el resto a
  0 como corresponde a un entorno de prueba sin facturas).

Estos números son de un volumen de datos pequeño (entorno de desarrollo); en producción, con más
facturas y OCR acumulado, backup y restore tardarán más — repetir esta medición contra un volumen
representativo real cuando exista (recomendación para la sesión de despliegue futuro, no bloquea esta
tarea).

## Pendiente de una sesión futura con acceso a infraestructura real

1. **Cron nocturno real en la VPS de producción**: un temporizador systemd o cron del sistema que
   invoque `backup_database.py` cada noche. Elegir la hora de menor carga (madrugada, hora española).
2. **Subida real a un destino externo (Hetzner Storage Box u otro)**: hoy el script escribe a una
   ruta de fichero local; conectar esa ruta a una subida real (rclone/rsync/SFTP) es responsabilidad
   de esa sesión futura, con las credenciales de Hetzner que Julio proporcione entonces.
3. **Política de retención**: cuántos backups diarios/semanales/mensuales conservar antes de borrar
   los más antiguos — decisión de negocio pendiente, no implementada.
4. **Verificar `max_connections`/espacio en disco de Hetzner** frente al tamaño real de los backups en
   producción, una vez exista ese volumen — mismo espíritu que la recomendación de `db_pool_size` de
   S5.5 frente a `max_connections` de Postgres.
5. **Rol de Postgres dedicado a backups** (en vez de reutilizar el DSN admin de las migraciones): mejora
   legítima de menor privilegio, decisión de infraestructura de producción (ver ADR-0019).

## Si se sospecha filtración de `BACKUP_ENCRYPTION_KEY`

A diferencia de `DB_ENCRYPTION_MASTER_KEY` (S5.2, con `jobs/key_rotation.py` +
`docs/runbooks/rotacion-clave-cifrado.md` para re-cifrar el histórico en vivo), **no hay ningún
mecanismo para "rotar" backups ya generados**: cada backup es un fichero estático cifrado con la
clave vigente en el momento de crearlo. Cambiar `BACKUP_ENCRYPTION_KEY` hace que **todos los backups
anteriores dejen de poder descifrarse con la clave nueva**. Ante sospecha de filtración:

1. Cambiar `BACKUP_ENCRYPTION_KEY` de inmediato para todos los backups FUTUROS.
2. Conservar la clave vieja por separado (nunca en el mismo sitio que la nueva) mientras los backups
   antiguos cifrados con ella sigan siendo necesarios para un restore real.
3. Si hace falta re-cifrar el histórico con la clave nueva (p. ej. por política de retención de
   secretos), descifrar cada backup con la clave vieja y volver a cifrarlo con la nueva
   (`shared.backup_encryption.decrypt_backup`/`encrypt_backup` directamente) — no hay script dedicado
   todavía, construirlo si esta operación se vuelve recurrente.

## Cuándo restaurar de verdad (no solo el drill)

Solo si se pierde la base de datos de producción (fallo de disco, corrupción, borrado accidental) o si
hace falta reconstruir un entorno desde un backup por cualquier otro motivo real. El restore real
sigue los mismos pasos que el drill, pero contra la base de datos de producción restaurada — **nunca
practicar el restore real directamente en producción sin haber hecho antes el drill contra una base
de datos vacía**, exactamente como exige el propio script (C4 de la spec).
