# Correr los tests del backend en local, en la VPS B

Esta VPS (`2.24.8.109`) es a la vez el sitio donde se hace desarrollo/pruebas Y donde vive el
despliegue real (`panel-staging`/`ilex`/`setex.autoken.es`, `infrastructure/`). Eso tiene una
consecuencia real que ya mordió una vez (2026-07-28): el `.env` del REPO (`/opt/app-facturas/.env`,
con las credenciales reales del despliegue) se carga automáticamente al correr `pytest` desde este
mismo checkout, aunque nadie lo pida explícitamente.

## El hallazgo (2026-07-28)

`shared/config.py` declara `Settings` con:

```python
model_config = SettingsConfigDict(env_file=_find_project_root() / ".env", ...)
```

`pydantic-settings` resuelve cada variable con esta prioridad: **variables de entorno reales del
proceso > valores del fichero `.env` > default del campo**. Como `/opt/app-facturas/.env` existe de
verdad en esta VPS (es el de producción), cualquier campo que ese fichero defina — por ejemplo
`MINIO_ENDPOINT=minio:9000`, `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` reales — se cuela en `Settings()`
durante un `pytest` local, EN VEZ DEL default de test (`localhost:9000` / `minioadmin`/`minioadmin`),
sin que ninguna variable de entorno lo haya pedido.

Síntoma real que costó diagnosticar: ~130 tests fallando con
`invoice_intake.storage.StorageUnavailable`, primero con
`NameResolutionError("...'minio'...")` (el hostname interno de Docker Compose no resuelve fuera de
esa red) y, tras apuntar a mano a `localhost:9000`, con `InvalidAccessKeyId` (las credenciales reales
del `.env` no son las del MinIO de test). El contenedor de test (`autoken-minio-test`) no tenía nada
que ver — se llegó a parar/recrear sin que cambiara el síntoma, antes de encontrar la causa real.

`DATABASE_URL` y `REDIS_URL` YA estaban protegidos de este mismo problema (fixture `authapi` en
`tests/conftest.py`): `DATABASE_URL` se sobreescribe siempre (fuerte), `REDIS_URL` con `setdefault`
(débil, respeta un valor ya puesto por CI). A `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`
les faltaba el mismo tratamiento — añadido ahora (`_TEST_MINIO_DEFAULTS`, mismo fixture).

## Por qué ya no debería repetirse

El fixture `authapi` (usado por todos los tests que arrancan la app de verdad, `tests/conftest.py`)
ahora fija con `os.environ.setdefault(...)` los tres valores de MinIO de test ANTES de que
`Settings()` los resuelva (`config.get_settings.cache_clear()` justo después) — como una variable de
entorno real siempre gana al `.env`, esto basta para que el `.env` real de esta VPS deje de colarse,
sin tocar nada del `.env` en sí. Restaurado al terminar el test, igual que `DATABASE_URL`/`REDIS_URL`.

**Si aun así vuelve a pasar** (un test nuevo que hable con MinIO SIN pasar por `authapi`, por
ejemplo): fijar las tres variables a mano antes de `pytest`:

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=minioadmin MINIO_SECRET_KEY=minioadmin \
    pytest -q
```

## Contenedores de dev/test en esta VPS (no versionados, no confundir con el despliegue real)

| Contenedor | Puerto host | Uso |
|---|---|---|
| `autoken-pg-dev` | 5432 | Postgres de desarrollo suelto (fuera de `infrastructure/`) |
| `autoken-pg-test` | 5433 | Postgres que usan los tests (`TEST_DATABASE_ADMIN_DSN`) |
| `autoken-redis-dev` | 6379 | Redis de desarrollo suelto |
| `autoken-redis-test` | 6380 | Redis de test |
| `autoken-minio-test` | 9000 | MinIO de test (`MINIO_ENDPOINT` de test) |
| `infrastructure-*` | — (red Docker interna) | El despliegue REAL (`docker compose` en `infrastructure/`), nunca usar para tests |

Si alguno de estos contenedores de dev/test lleva mucho tiempo arriba y da errores raros de disco
(ver logs con `docker logs <nombre>`), es seguro pararlo, borrarlo junto a su volumen, y recrearlo
limpio con la misma imagen/puerto/credenciales — no contienen datos reales, solo lo que hayan dejado
sesiones de test anteriores.
