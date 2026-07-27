#!/usr/bin/env bash
# Backup nocturno real de la base de datos (S5.3): genera el volcado cifrado con el mecanismo ya
# construido y probado (backend/src/jobs/backup.py) y lo sube por SSH a una VPS DISTINTA
# físicamente de la que sirve la app (defensa contra perder ambas a la vez). Pensado para
# invocarse desde cron; también se puede lanzar a mano para probarlo.
#
# Requiere en ../.env: POSTGRES_ADMIN_USER/POSTGRES_ADMIN_PASSWORD/POSTGRES_DB (ya puestos),
# BACKUP_ENCRYPTION_KEY (ya puesto). Requiere la clave SSH ~/.ssh/autoken_deploy_backups con
# acceso ya autorizado en la VPS de destino (ver docs/runbooks/backups-restore.md).
set -euo pipefail
cd "$(dirname "$0")"

BACKUP_HOST="${BACKUP_HOST:-72.62.189.27}"
BACKUP_SSH_KEY="${BACKUP_SSH_KEY:-$HOME/.ssh/autoken_deploy_backups}"
BACKUP_REMOTE_DIR="${BACKUP_REMOTE_DIR:-/opt/autoken-backups/panel-staging}"
COMPOSE_NETWORK="${COMPOSE_NETWORK:-infrastructure_default}"

TIMESTAMP="$(date +%F_%H%M%S)"
BACKUP_NAME="autoken-panel-staging-${TIMESTAMP}.enc"
LOCAL_BACKUP_PATH="/tmp/${BACKUP_NAME}"

# DSN admin + clave de cifrado en un fichero de entorno TEMPORAL, solo para este `docker run` (nunca
# como argumento de línea de comandos, nunca en el .env compartido de api/worker — ver ADR-0019).
RUN_ENV_FILE="$(mktemp)"
chmod 600 "$RUN_ENV_FILE"
trap 'rm -f "$RUN_ENV_FILE" "$LOCAL_BACKUP_PATH"' EXIT


# Extrae SOLO las 4 claves que hacen falta, sin `source` de todo el fichero: `.env` puede tener
# líneas que no son bash válido (comentarios/valores con formato libre de otras integraciones) y
# `source` entero fallaría por una línea que no nos afecta.
_env_get() {
  grep -m1 "^$1=" ../.env | cut -d'=' -f2- || true
}
_pg_admin_user="$(_env_get POSTGRES_ADMIN_USER)"
_pg_admin_password="$(_env_get POSTGRES_ADMIN_PASSWORD)"
_pg_db="$(_env_get POSTGRES_DB)"
_backup_key="$(_env_get BACKUP_ENCRYPTION_KEY)"

{
  echo "BACKUP_DATABASE_ADMIN_DSN=postgresql://${_pg_admin_user:-postgres}:${_pg_admin_password}@postgres:5432/${_pg_db:-autoken}"
  echo "BACKUP_ENCRYPTION_KEY=${_backup_key}"
} > "$RUN_ENV_FILE"

docker build --target ops -q -t autoken/ops:latest ../backend >/dev/null

# `--user` = el uid/gid de quien ejecuta el script (no el `appuser` de la imagen): así el fichero
# que aparece en /tmp del host lo puede borrar luego este mismo proceso (si no, "Operation not
# permitted" al limpiar — fallo real visto en la primera prueba).
docker run --rm \
  --network "$COMPOSE_NETWORK" \
  --env-file "$RUN_ENV_FILE" \
  --user "$(id -u):$(id -g)" \
  -v /tmp:/backups \
  autoken/ops:latest scripts/backup_database.py --output "/backups/${BACKUP_NAME}"

scp -i "$BACKUP_SSH_KEY" -o StrictHostKeyChecking=accept-new \
  "$LOCAL_BACKUP_PATH" "root@${BACKUP_HOST}:${BACKUP_REMOTE_DIR}/"

echo "Backup subido: ${BACKUP_REMOTE_DIR}/${BACKUP_NAME} (en ${BACKUP_HOST})"
