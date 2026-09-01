#!/usr/bin/env bash
set -Eeuo pipefail

# Único punto de entrada para staging/producción. El Compose base sigue siendo válido para desarrollo,
# pero nunca debe ser el comando de despliegue público: el overlay añade la red y los routers Traefik.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infrastructure"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
HEALTHCHECK_HOSTS="${HEALTHCHECK_HOSTS:-panel-staging.autoken.es}"

if [[ ! -f "$ENV_FILE" ]]; then
  printf 'Falta el fichero de entorno: %s\n' "$ENV_FILE" >&2
  exit 1
fi

compose=(
  docker compose
  --env-file "$ENV_FILE"
  --project-directory "$INFRA_DIR"
  -f "$INFRA_DIR/docker-compose.yml"
  -f "$INFRA_DIR/docker-compose.prod.yml"
)

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

docker network inspect proxy >/dev/null 2>&1 || die "no existe la red Docker externa proxy"
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait

api_id="$("${compose[@]}" ps -q api)"
frontend_id="$("${compose[@]}" ps -q frontend)"
[[ -n "$api_id" && -n "$frontend_id" ]] || die "Compose no ha creado API y frontend"

api_env="$(docker inspect --format '{{json .Config.Env}}' "$api_id")"
api_profile="$(python3 -c 'import json, sys; values=json.load(sys.stdin); print(next((v.split("=", 1)[1] for v in values if v.startswith("DEPLOYMENT_PROFILE=")), ""))' <<<"$api_env")"
[[ "$api_profile" == "proxy" ]] || die "API no tiene DEPLOYMENT_PROFILE=proxy"

worker_id="$("${compose[@]}" ps -q worker)"
[[ -n "$worker_id" ]] || die "Compose no ha creado el worker"
worker_env="$(docker inspect --format '{{json .Config.Env}}' "$worker_id")"
worker_profile="$(python3 -c 'import json, sys; values=json.load(sys.stdin); print(next((v.split("=", 1)[1] for v in values if v.startswith("DEPLOYMENT_PROFILE=")), ""))' <<<"$worker_env")"
[[ "$worker_profile" == "proxy" ]] || die "worker no tiene DEPLOYMENT_PROFILE=proxy"

api_labels="$(docker inspect --format '{{json .Config.Labels}}' "$api_id")"
python3 - "$api_labels" <<'PY'
import json
import sys

labels = json.loads(sys.argv[1])
if labels.get("traefik.docker.network") != "proxy":
    raise SystemExit("API no declara traefik.docker.network=proxy")
if not any(
    key.startswith("traefik.http.routers.") and key.endswith("-api.rule")
    for key in labels
):
    raise SystemExit("API no declara ningún router Traefik para /api")
PY

IFS=',' read -r -a health_hosts <<<"$HEALTHCHECK_HOSTS"
for host in "${health_hosts[@]}"; do
  host="${host//[[:space:]]/}"
  [[ -n "$host" ]] || continue
  health_body="$(curl --fail --silent --show-error --max-time 15 "https://$host/api/v1/health")" \
    || die "health público fallido en $host"
  python3 -c 'import json, sys; body=json.load(sys.stdin); assert body.get("status") == "ok"' <<<"$health_body" \
    || die "health público no devolvió status=ok en $host"
done

printf 'Despliegue proxy verificado: API, frontend, red proxy, routers Traefik y health público.\n'
