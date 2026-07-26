# ADR-0019: Cifrado y alcance del backup de base de datos

- **Estado**: aceptado
- **Fecha**: 2026-07-26
- **Decisores**: Julio (+ Claude Code)

## Contexto

El plan maestro exige (S5.3) un backup nocturno cifrado de la base de datos a un destino externo
(Hetzner) y un simulacro de restore documentado con tiempos. Este entorno de trabajo no tiene
credenciales de ningún destino externo real; Julio confirmó explícitamente (spec §0) construir el
mecanismo completo y verificable en este entorno, dejando el cron real y la subida a Hetzner
pendientes de una sesión futura con esa infraestructura.

Quedaban dos decisiones de diseño que sí afectan al código de esta tarea: cómo cifrar el backup, y
si compartir o no la clave de cifrado en reposo por tenant (S5.2, ADR-0018).

## Decisión

### Mecanismo: `pg_dump --format=custom` + AES-256-GCM en la aplicación, no pgcrypto

A diferencia de ADR-0018 (cifrado de columnas dentro de Postgres, vía `pgp_sym_encrypt`), el backup
se cifra en la aplicación, después de que `pg_dump` produzca el volcado: no hay forma de pedirle a
`pg_dump` que cifre su salida dentro de Postgres, el cifrado tiene que ocurrir sobre el fichero ya
volcado. Se usa AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`, ya dependencia del
proyecto desde S5.2) en vez de reimplementar algo con pgcrypto: GCM autentica el contenido (una clave
incorrecta o un fichero corrupto fallan alto y claro, nunca "restauran basura"), y no necesita
Postgres de por medio para cifrar/descifrar (el propio operador, fuera de cualquier conexión a la
base de datos, puede verificar un backup).

### Clave del backup: secreto DISTINTO de `DB_ENCRYPTION_MASTER_KEY`

`BACKUP_ENCRYPTION_KEY` es un secreto nuevo, nunca el mismo que `DB_ENCRYPTION_MASTER_KEY` (S5.2).
Motivo: protegen modelos de amenaza distintos. `DB_ENCRYPTION_MASTER_KEY` protege columnas
individuales dentro de una base de datos viva y accesible; `BACKUP_ENCRYPTION_KEY` protege un fichero
completo que sale de la base de datos y viaja a un almacenamiento externo (con su propio riesgo de
filtración — un proveedor de backups comprometido, un fichero mal permisado). Si compartieran la
misma clave, filtrar cualquiera de los dos secretos comprometería ambos mecanismos a la vez; con
claves separadas, cada una se puede rotar de forma independiente sin afectar a la otra.

### Alcance: solo backup completo (`pg_dump`), sin incrementales ni WAL

Se descarta explícitamente el archivado de WAL / point-in-time recovery para esta tarea: añade
complejidad operativa real (un servidor de archivado de WAL, gestión de la ventana de retención) que
el plan maestro no pide todavía (su CA es "backup nocturno... funcionando", no "recuperación a
cualquier punto en el tiempo"). Un backup completo nocturno con un RPO de 24h es la decisión de
alcance mínimo correcta para esta fase del proyecto; si el negocio necesita un RPO menor más adelante,
es una decisión de producto nueva, no un ajuste de esta tarea.

### DSN admin del backup: se reutiliza la credencial que ya usan las migraciones

No se crea un rol de Postgres nuevo para backups. El volcado necesita ver TODAS las filas de TODOS
los tenants (RLS, ADR-0001, lo impediría con el rol runtime restringido) — se reutiliza el mismo tipo
de credencial de superusuario/bypass-RLS que ya usan Alembic y `rotate_encryption_key.py` (S5.2).
Introducir un rol de backup dedicado con permisos más ajustados es una mejora legítima, pero una
decisión de infraestructura de producción, no de esta tarea (§6 de la spec).

### `BACKUP_ENCRYPTION_KEY` NO se valida en `Settings` (a diferencia de `JWT_SECRET`/`DB_ENCRYPTION_MASTER_KEY`)

Hallazgo de auditoría: la primera versión de esta tarea añadió un `model_validator` global (mismo
patrón que `jwt_secret`/`db_encryption_master_key`) que rechazaba un `backup_encryption_key`
inseguro al construir `Settings` en producción. Eso obligaba a que la API y el worker (que
construyen `Settings` en cada arranque, y comparten `env_file: ../.env` en
`infrastructure/docker-compose.yml`, SIN lista blanca de variables) tuvieran ese secreto en su
propio entorno para poder arrancar en producción, aunque ninguno de los dos lo usa jamás —
deshaciendo exactamente el aislamiento que esta ADR decide más arriba. Corregido: la comprobación de
fortaleza (`shared.config.require_strong_backup_encryption_key`) es una función normal, llamada
explícitamente solo desde `scripts/backup_database.py`/`scripts/restore_drill.py` — los únicos
consumidores reales del secreto.

## Consecuencias

- Dos secretos de cifrado que rotar por separado (`DB_ENCRYPTION_MASTER_KEY`, `BACKUP_ENCRYPTION_KEY`)
  — más entradas en el mapa de secretos (`CLAUDE.md` §9.1), pero aislamiento real entre ambos riesgos.
- El backup completo de una base de datos con mucho volumen puede tardar minutos y ocupar
  varios GB — aceptable para el tamaño actual del proyecto (multi-tenant compartido, no vídeo/objetos
  binarios grandes en la propia base de datos, esos viven en MinIO); si el volumen crece mucho, revisar
  esta ADR.
- El restore drill exige una base de datos destino completamente vacía por diseño (defensa contra
  sobrescribir por error un entorno con datos reales) — automatizar la creación de esa base vacía en
  el pipeline de backup real de producción es parte del trabajo pendiente documentado en
  `docs/runbooks/backups-restore.md`.
