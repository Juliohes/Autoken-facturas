# Spec: BP-3 Inyección de `Settings` en el healthcheck (DIP, no service-locator)

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** BP-3 (hallazgo de `Auditoria_Autoken_Javi_22-06-2026.md`)
- **Contexto (módulo):** platform (`backend/src/platform_admin/health.py`)
- **ADR relacionados:** — (principio SOLID/DIP; sistema `Depends` de FastAPI)
- **Estado:** aprobada por Julio (2026-06-29)

## 1. Problema y valor de dominio
El handler `health()` llama a `get_settings()` **dentro** de la función (patrón *service locator*) en vez de
recibirlo como dependencia inyectada (`Depends(get_settings)`). Consecuencias:
- Rompe la inversión de dependencias (DIP): el endpoint conoce y resuelve su propia dependencia en vez de
  declararla y dejar que el framework la provea.
- **Los tests no pueden sustituir la configuración** con `app.dependency_overrides[get_settings]`: la llamada
  directa ignora cualquier override, así que no hay forma limpia de probar el endpoint con un entorno simulado
  (p. ej. comprobar que refleja `production` sin tocar variables de entorno del proceso).

Valor: que el endpoint declare su dependencia de configuración por inyección, de modo que sea **sustituible en
test** (y, a futuro, por tenant/entorno) sin parchear módulos ni variables de entorno globales.

## 2. Lenguaje ubicuo
- **Dependencia inyectada (`Depends`)**: FastAPI resuelve `get_settings` y la pasa como argumento al handler.
- **Override de dependencia**: `app.dependency_overrides[get_settings] = ...` sustituye esa dependencia en test.
- **Service locator**: antipatrón en que el código pide su dependencia a un proveedor global en vez de recibirla.

## 3. Comportamientos (criterios de aceptación)

### C1 — El healthcheck refleja la configuración inyectada (sustituible en test)  *(el núcleo de BP-3)*
- **Given** un override de `get_settings` que devuelve una `Settings` con `app_name`, `app_version` y `app_env`
  distintos de los del proceso (p. ej. nombre "Servicio de prueba", versión "9.9.9", entorno `production`)
- **When** se pide `GET /api/v1/health`
- **Then** la respuesta refleja esos valores inyectados (`service`, `version`, `environment`), demostrando que
  la dependencia es sustituible (hoy esto falla: el override no tiene efecto)

### C2 — Sin override, el healthcheck sigue respondiendo con la configuración real
- **Given** ningún override de dependencias
- **When** se pide `GET /api/v1/health`
- **Then** responde 200 con `status="ok"` y los metadatos reales del servicio (no se rompe el comportamiento
  existente; los tests actuales de 0.4 siguen verdes)

## 4. Invariantes y reglas de negocio
- **DIP:** el handler no resuelve su propia configuración; la declara como parámetro `Depends(get_settings)`.
- **Contrato HTTP intacto:** mismo path, mismo `HealthResponse` (status, service, version, environment), mismo
  comportamiento observable cuando no hay override. BP-3 es refactor de testabilidad, no cambio de contrato.
- **`get_settings` sigue cacheado** (`@lru_cache`) en producción; el override solo aplica en test.

## 5. Casos límite y errores
- El test que usa override debe **limpiar** `app.dependency_overrides` al terminar para no contaminar otros
  tests (la app es un singleton de módulo, compartido por la fixture `client`).

## 6. Fuera de alcance (no-objetivos)
- Inyectar `Settings` en otros puntos (`main.create_app` usa `get_settings()` en el arranque; ahí no es un
  handler y queda fuera de BP-3).
- Cambiar la firma o el cacheo de `get_settings`.
- Añadir comprobaciones de salud reales (BD, dependencias externas): el healthcheck sigue siendo liveness.

## 7. Notas de verificación
- Tests en `backend/tests/test_health.py`, estilo existente (cliente ASGI async).
- C1: `app.dependency_overrides[get_settings] = lambda: Settings(app_name=..., app_version=..., app_env=...)`
  dentro de `try/finally` que limpia los overrides.
- **Diseño elegido:** `async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse`.
